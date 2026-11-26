"""Energy saving advice.

Pure functions (no Home Assistant imports) that turn the learned room models
and the data of the last days into concrete tips with an estimated saving.

The physics is the same simple model the thermal learner uses: a room loses
heat proportional to the difference with outside (Newton cooling, rate k per
hour). Over a whole day the gas used for heating a room is proportional to
the time integral of (T_inside − T_outside). Anything that keeps a room cooler
for a while (lower day temperature, a night setback including the reheat
afterwards) saves the fraction ∫reduction dt / (24 h · ΔT) of its heating gas.

The estimates are calibrated with what was actually measured since the start
of the savings measurement, so they improve as more days come in.
"""

from __future__ import annotations

from bisect import bisect_right
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
import math
from typing import Any

DEFAULT_COOLING = 0.03  # 1/h, a typical well-insulated house with floor heating
DEFAULT_HEAT_RATE = 0.5  # °C/h net reheat rate when nothing was learned yet
DAYS_PER_MONTH = 30
MIN_MEASURED_DAYS = 3  # before this, the measurement is not used to calibrate
FULL_CALIBRATION_DAYS = 14
MAX_OFFSET = 4.0  # deepest night setback that is suggested


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class RoomInput:
    """What is known about one room."""

    room_id: str
    name: str
    weight: float = 1.0  # relative size (number of floor heating loops)
    day_target: float | None = None  # mean day setpoint (last days)
    night_target: float | None = None  # mean night setpoint (last days)
    measured: float | None = None  # mean measured temperature (last days)
    cooling: float | None = None  # learned k (1/h)
    heat_rate: float | None = None  # learned net reheat rate (°C/h)
    confidence: int = 0
    setback_enabled: bool = True
    night_hours: float = 9.0
    offset: float = -2.0  # effective night setback (°C, ≤ 0)
    uses_global: bool = True
    optimum_start: bool = False
    label: str | None = None  # ranking label ("Hoog warmteverlies", …)


@dataclass(slots=True)
class HouseInput:
    """House wide figures of the last days."""

    outdoor_mean: float | None
    heating_gas_per_day: float | None  # m³/day used for heating
    gas_price: float
    days: int = 0  # number of recent days the figures are based on
    measured_days: int = 0  # complete days since the savings start
    measured_expected: float = 0.0  # Σ expected gas on those days
    measured_actual: float = 0.0  # Σ actual gas on those days
    master_enabled: bool = True
    global_offset: float = -2.0
    global_hours: float = 9.0
    boiler_cycling: bool = False


@dataclass(slots=True)
class Tip:
    """A single piece of advice."""

    id: str
    category: str  # "measurement", "night", "day", "room", "boiler"
    title: str
    text: str
    saving_m3_month: float | None = None
    saving_eur_month: float | None = None
    confidence: str = "laag"  # laag / redelijk / goed
    room_id: str | None = None
    details: list[str] = field(default_factory=list)
    priority: float = 0.0


# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
def setback_degree_hours(
    delta_t: float, cooling: float, offset: float, hours: float, heat_rate: float
) -> float:
    """Degree hours (°C·h) a room stays below its day temperature in one night.

    The room cools freely towards outside after the setback starts until it
    reaches the lowered setpoint; when the night ends it warms back up at the
    (net) heating rate. Both phases count as saving.
    """
    depth = abs(offset)
    if delta_t <= 0 or depth <= 0 or hours <= 0:
        return 0.0
    k = max(cooling, 1e-4)
    if depth < delta_t:
        reach = -math.log(1 - depth / delta_t) / k
    else:
        reach = math.inf
    if reach >= hours:
        area = delta_t * (hours - (1 - math.exp(-k * hours)) / k)
        drop = delta_t * (1 - math.exp(-k * hours))
    else:
        area = delta_t * (reach - (1 - math.exp(-k * reach)) / k) + depth * (hours - reach)
        drop = depth
    rate = heat_rate if heat_rate and heat_rate > 0.05 else DEFAULT_HEAT_RATE
    return area + drop * drop / (2 * rate)


def night_drop(delta_t: float, cooling: float, offset: float, hours: float) -> float:
    """How far the room actually cools during the night (°C)."""
    if delta_t <= 0 or hours <= 0:
        return 0.0
    free = delta_t * (1 - math.exp(-max(cooling, 1e-4) * hours))
    return min(abs(offset), free)


# ---------------------------------------------------------------------------
# Recorder history → setpoints per room
# ---------------------------------------------------------------------------
Sample = tuple[datetime, float | None, float | None]  # (time, target, measured)


def in_night(moment: time, start: time, end: time) -> bool:
    """Whether a local time of day lies in the night window."""
    if start <= end:
        return start <= moment < end
    return moment >= start or moment < end


def summarize_setpoints(
    series: list[list[Sample]],
    start: datetime,
    end: datetime,
    night_start: time,
    night_end: time,
    step: timedelta = timedelta(minutes=15),
    to_local=lambda moment: moment,
) -> dict[str, float | None]:
    """Time weighted mean day/night setpoint and measured temperature.

    ``series`` holds one list of samples per thermostat (sorted by time); the
    value of a sample holds until the next one.
    """
    times = [[s[0] for s in samples] for samples in series]
    sums = {"day": [0.0, 0], "night": [0.0, 0], "measured": [0.0, 0]}
    moment = start
    while moment < end:
        targets = []
        measured = []
        for samples, stamps in zip(series, times, strict=True):
            index = bisect_right(stamps, moment) - 1
            if index < 0:
                continue
            _, target, current = samples[index]
            if target is not None:
                targets.append(target)
            if current is not None:
                measured.append(current)
        if targets:
            key = "night" if in_night(to_local(moment).time(), night_start, night_end) else "day"
            sums[key][0] += sum(targets) / len(targets)
            sums[key][1] += 1
        if measured:
            sums["measured"][0] += sum(measured) / len(measured)
            sums["measured"][1] += 1
        moment += step
    return {key: (total / count if count else None) for key, (total, count) in sums.items()}


# ---------------------------------------------------------------------------
# Advice
# ---------------------------------------------------------------------------
def _hours(start: time, end: time) -> float:
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    if minutes <= 0:
        minutes += 24 * 60
    return minutes / 60


def window_hours(start: time, end: time) -> float:
    """Length of a night window in hours."""
    return _hours(start, end)


def _delta(room: RoomInput, outdoor: float) -> float | None:
    inside = room.measured if room.measured is not None else room.day_target
    if inside is None:
        return None
    return max(0.0, inside - outdoor)


def _k(room: RoomInput) -> float:
    return room.cooling if room.cooling else DEFAULT_COOLING


def _shares(rooms: list[RoomInput], outdoor: float) -> dict[str, float]:
    """Share of the heating gas per room (weight × ΔT)."""
    loads = {r.room_id: r.weight * (_delta(r, outdoor) or 0.0) for r in rooms}
    total = sum(loads.values())
    if total <= 0:
        return {r.room_id: 1 / len(rooms) for r in rooms} if rooms else {}
    return {room_id: load / total for room_id, load in loads.items()}


def _fraction_night(room: RoomInput, outdoor: float, offset: float, hours: float) -> float:
    delta = _delta(room, outdoor)
    if not delta:
        return 0.0
    area = setback_degree_hours(delta, _k(room), offset, hours, room.heat_rate or 0.0)
    return area / (24 * delta)


def _confidence(rooms: list[RoomInput], calibrated: bool) -> str:
    if not rooms:
        return "laag"
    mean = sum(r.confidence for r in rooms) / len(rooms)
    if calibrated and mean >= 50:
        return "goed"
    if calibrated or mean >= 50:
        return "redelijk"
    return "laag"


def _fmt(value: float, digits: int = 1) -> str:
    text = f"{value:.{digits}f}".replace(".", ",")
    return "0" if text in ("-0", "-0,0") else text


class _Builder:
    def __init__(self, house: HouseInput, factor: float) -> None:
        self.house = house
        self.factor = factor
        self.tips: list[Tip] = []

    def money(self, m3_per_day: float) -> tuple[float, float]:
        month = m3_per_day * DAYS_PER_MONTH * self.factor
        return round(month, 1), round(month * self.house.gas_price, 2)

    def add(self, tip: Tip, m3_per_day: float | None = None) -> None:
        if m3_per_day is not None:
            tip.saving_m3_month, tip.saving_eur_month = self.money(m3_per_day)
            tip.priority = tip.saving_eur_month
        self.tips.append(tip)


def calibration(house: HouseInput, predicted_fraction: float) -> tuple[float, float | None]:
    """Correction factor from the measured savings (1.0 = model as is).

    Returns (factor, measured fraction). The factor moves from 1 towards
    measured/predicted as more days are measured.
    """
    if house.measured_days < MIN_MEASURED_DAYS or house.measured_expected <= 0:
        return 1.0, None
    measured = (house.measured_expected - house.measured_actual) / house.measured_expected
    if predicted_fraction <= 0.005:
        return 1.0, measured
    raw = min(2.5, max(0.3, measured / predicted_fraction))
    weight = min(1.0, house.measured_days / FULL_CALIBRATION_DAYS)
    return 1 + (raw - 1) * weight, measured


def build_advice(rooms: list[RoomInput], house: HouseInput) -> dict[str, Any]:
    """Return the tips (most valuable first) and the figures they are based on."""
    outdoor = house.outdoor_mean
    gas = house.heating_gas_per_day
    usable = outdoor is not None and gas is not None and gas > 0 and rooms
    shares = _shares(rooms, outdoor) if usable else {}

    def night_now(room: RoomInput) -> float:
        if not (house.master_enabled and room.setback_enabled):
            return 0.0
        return _fraction_night(room, outdoor, room.offset, room.night_hours)

    predicted = sum(shares[r.room_id] * night_now(r) for r in rooms) if usable else 0.0
    factor, measured = calibration(house, predicted)
    calibrated = house.measured_days >= MIN_MEASURED_DAYS
    b = _Builder(house, factor)

    # ---- 1. what was measured so far ---------------------------------
    if house.measured_days == 0:
        b.add(
            Tip(
                "measurement",
                "measurement",
                "Meting gestart",
                "De besparing wordt per volledige dag gemeten. Na de eerste nacht zie je "
                "morgen hoeveel gas er is bespaard ten opzichte van de referentie; na "
                f"{MIN_MEASURED_DAYS} dagen worden de schattingen hieronder bijgesteld "
                "met wat er echt gemeten is.",
                priority=1e6,
            )
        )
    else:
        saved = house.measured_expected - house.measured_actual
        pct = 100 * saved / house.measured_expected if house.measured_expected else 0.0
        text = (
            f"{house.measured_days} volledige dag{'en' if house.measured_days != 1 else ''} "
            f"gemeten: {_fmt(house.measured_actual)} m³ verbruikt, {_fmt(house.measured_expected)} m³ "
            f"verwacht zonder maatregelen. Dat is {_fmt(saved)} m³ "
            f"({_fmt(pct, 0)} %) {'bespaard' if saved >= 0 else 'méér verbruikt'}."
        )
        if usable and predicted > 0:
            text += f" Het model voorspelde {_fmt(100 * predicted, 0)} %."
        if not calibrated:
            text += (
                f" Nog {MIN_MEASURED_DAYS - house.measured_days} dag(en) tot de schattingen "
                "hierop worden afgestemd – één dag zegt nog weinig (weer, wind, zon, tapwater)."
            )
        elif abs(factor - 1) > 0.05:
            text += (
                f" De schattingen hieronder zijn daarom met factor {_fmt(factor, 2)} bijgesteld."
            )
        b.add(Tip("measurement", "measurement", "Gemeten resultaat", text, priority=1e6))

    if not usable:
        b.add(
            Tip(
                "no-data",
                "measurement",
                "Nog te weinig gegevens",
                "Voor schattingen zijn de buitentemperatuur, het gasverbruik van de laatste "
                "dagen, een baseline en minimaal één kamer nodig.",
            )
        )
        return _result(b, rooms, house, shares, predicted, factor, measured)

    # ---- 2. night setback ---------------------------------------------
    enabled = [r for r in rooms if house.master_enabled and r.setback_enabled]
    disabled = [r for r in rooms if not (house.master_enabled and r.setback_enabled)]
    if disabled:
        per_day = sum(
            shares[r.room_id] * _fraction_night(r, outdoor, r.offset, r.night_hours)
            for r in disabled
        ) * gas
        names = ", ".join(r.name for r in disabled)
        b.add(
            Tip(
                "night-enable",
                "night",
                "Nachtverlaging aanzetten",
                f"Nachtverlaging staat uit voor: {names}. Met de huidige instellingen "
                "levert aanzetten naar schatting het bedrag hiernaast op.",
                confidence=_confidence(disabled, calibrated),
            ),
            per_day,
        )
    if enabled:
        deeper = []
        earlier = []
        slow = []
        for r in enabled:
            share = shares[r.room_id]
            now = _fraction_night(r, outdoor, r.offset, r.night_hours)
            depth = max(-MAX_OFFSET, r.offset - 1)
            deeper.append((r, share * (_fraction_night(r, outdoor, depth, r.night_hours) - now)))
            earlier.append(
                (r, share * (_fraction_night(r, outdoor, r.offset, r.night_hours + 1) - now))
            )
            delta = _delta(r, outdoor) or 0.0
            drop = night_drop(delta, _k(r), r.offset, r.night_hours)
            if r.cooling and r.confidence >= 40 and drop < 0.6 * abs(r.offset):
                slow.append((r, drop))
        deeper_day = sum(v for _, v in deeper) * gas
        earlier_day = sum(v for _, v in earlier) * gas
        conf = _confidence(enabled, calibrated)
        global_offset = house.global_offset
        if global_offset > -MAX_OFFSET and deeper_day > 0:
            top = sorted(deeper, key=lambda x: -x[1])[:3]
            b.add(
                Tip(
                    "night-deeper",
                    "night",
                    f"Nachtverlaging 1 °C dieper ({_fmt(global_offset)} → "
                    f"{_fmt(max(-MAX_OFFSET, global_offset - 1))} °C)",
                    "Een diepere verlaging helpt alleen als de kamer 's nachts ook echt zo ver "
                    "afkoelt. Bij vloerverwarming gaat dat langzaam, en 's ochtends moet de "
                    "warmte weer terug – daarom is het effect kleiner dan je zou verwachten.",
                    confidence=conf,
                    details=[f"{r.name}: {_fmt(100 * v / max(1e-9, sum(x for _, x in deeper)), 0)} % van dit effect" for r, v in top if v > 0],
                ),
                deeper_day,
            )
        if earlier_day > 0:
            b.add(
                Tip(
                    "night-earlier",
                    "night",
                    "Nachtverlaging een uur eerder laten beginnen",
                    "Door de traagheid van vloerverwarming merk je een uur eerder verlagen "
                    "nauwelijks; de kamer koelt pas na een paar uur echt af. Het levert wel een "
                    "langere periode met minder warmteverlies op.",
                    confidence=conf,
                ),
                earlier_day,
            )
        for r, drop in slow:
            b.add(
                Tip(
                    f"slow-{r.room_id}",
                    "room",
                    f"{r.name}: koelt 's nachts maar ~{_fmt(drop)} °C af",
                    f"Het geleerde model laat zien dat {r.name} in {_fmt(r.night_hours, 0)} uur "
                    f"slechts ongeveer {_fmt(drop)} °C afkoelt, minder dan de ingestelde "
                    f"{_fmt(abs(r.offset))} °C. Dieper verlagen heeft hier dus weinig zin; "
                    "eerder beginnen of overdag iets lager wel.",
                    room_id=r.room_id,
                    confidence="redelijk" if r.confidence < 70 else "goed",
                    priority=0.1,
                )
            )

    # ---- 3. day temperature -------------------------------------------
    whole_day = 0.0
    for r in rooms:
        delta = _delta(r, outdoor)
        if not delta:
            continue
        # A relative night setback follows the day temperature, so the whole
        # day (24 h) is 0.5 °C cooler.
        whole_day += shares[r.room_id] * 0.5 / delta
    if whole_day > 0:
        b.add(
            Tip(
                "day-lower",
                "day",
                "Overal 0,5 °C lager",
                "Een halve graad lager merk je meestal nauwelijks, maar het scheelt de hele "
                "dag warmteverlies. Een vuistregel is 3–4 % gas per halve graad; deze schatting "
                "gebruikt het verschil tussen binnen en buiten van de laatste dagen.",
                confidence=_confidence(rooms, calibrated),
            ),
            whole_day * gas,
        )
    targets = [r.day_target for r in rooms if r.day_target is not None]
    if len(targets) >= 2:
        mean_target = sum(targets) / len(targets)
        for r in rooms:
            if r.day_target is None or r.day_target < max(21.0, mean_target + 0.75):
                continue
            delta = _delta(r, outdoor)
            if not delta:
                continue
            lower = round((r.day_target - max(20.0, mean_target)) * 2) / 2
            if lower < 0.5:
                continue
            per_day = shares[r.room_id] * lower / delta * gas
            b.add(
                Tip(
                    f"warm-{r.room_id}",
                    "day",
                    f"{r.name} staat warmer dan de rest ({_fmt(r.day_target)} °C)",
                    f"Gemiddeld stond {r.name} de afgelopen {house.days} dagen overdag op "
                    f"{_fmt(r.day_target)} °C, tegen {_fmt(mean_target)} °C gemiddeld in huis. "
                    f"{_fmt(lower)} °C lager levert naar schatting het bedrag hiernaast op.",
                    room_id=r.room_id,
                    confidence=_confidence([r], calibrated),
                ),
                per_day,
            )

    # ---- 4. room observations ------------------------------------------
    for r in rooms:
        if r.measured is None or r.day_target is None:
            continue
        diff = r.measured - (r.day_target if r.night_target is None else (r.day_target + r.night_target) / 2)
        if diff > 0.8:
            b.add(
                Tip(
                    f"above-{r.room_id}",
                    "room",
                    f"{r.name} is warmer dan ingesteld",
                    f"Gemeten gemiddeld {_fmt(r.measured)} °C terwijl de thermostaat lager stond. "
                    "De warmte komt dan van elders (zon, andere kamers, openhaard, apparaten); "
                    "de thermostaat lager zetten bespaart hier weinig.",
                    room_id=r.room_id,
                    priority=0.05,
                )
            )
        elif diff < -0.8:
            b.add(
                Tip(
                    f"below-{r.room_id}",
                    "room",
                    f"{r.name} haalt de ingestelde temperatuur niet",
                    f"Gemeten gemiddeld {_fmt(r.measured)} °C, ingesteld {_fmt(r.day_target)} °C "
                    "overdag. Mogelijk is de aanvoertemperatuur te laag, staat er een lus dicht of "
                    "koelt de kamer sterk af. Hoger zetten helpt dan niet; controleer lussen en "
                    "ventilatie.",
                    room_id=r.room_id,
                    priority=0.05,
                )
            )
        if r.label == "Hoog warmteverlies":
            b.add(
                Tip(
                    f"loss-{r.room_id}",
                    "room",
                    f"{r.name} verliest relatief veel warmte",
                    "Deze kamer koelt het snelst af van alle kamers. Controleer ramen, deuren, "
                    "roosters en kieren; dicht houden van de deur naar koudere ruimtes helpt ook.",
                    room_id=r.room_id,
                    priority=0.04,
                )
            )

    optimum = [
        r
        for r in rooms
        if not r.optimum_start
        and r.confidence >= 50
        and house.master_enabled
        and r.setback_enabled
    ]
    if optimum:
        b.add(
            Tip(
                "optimum-start",
                "night",
                "Optimum start aanzetten",
                "Het geleerde model is betrouwbaar genoeg voor: "
                + ", ".join(r.name for r in optimum)
                + ". Met optimum start begint het opwarmen zo laat mogelijk, zodat de "
                "verlaging langer duurt zonder dat het 's ochtends koud is. Instellen op het "
                "tabblad Schema's (\"op temperatuur om\").",
                priority=0.03,
            )
        )

    # ---- 5. boiler ------------------------------------------------------
    if house.boiler_cycling:
        b.add(
            Tip(
                "boiler-cycling",
                "boiler",
                "Ketel pendelt: aanvoertemperatuur verlagen",
                "De brander slaat vaak kort aan. Een lagere aanvoertemperatuur (stooklijn) of "
                "een lager minimaal vermogen laat de ketel langer en efficiënter branden. "
                "Grove schatting: 2–5 % van het verwarmingsgas.",
                confidence="laag",
            ),
            0.03 * gas,
        )
    return _result(b, rooms, house, shares, predicted, factor, measured)


def _result(b, rooms, house, shares, predicted, factor, measured) -> dict[str, Any]:
    tips = sorted(b.tips, key=lambda t: -t.priority)
    return {
        "tips": [
            {
                "id": t.id,
                "category": t.category,
                "title": t.title,
                "text": t.text,
                "saving_m3_month": t.saving_m3_month,
                "saving_eur_month": t.saving_eur_month,
                "confidence": t.confidence,
                "room_id": t.room_id,
                "details": t.details,
            }
            for t in tips
        ],
        "basis": {
            "days": house.days,
            "outdoor_mean": house.outdoor_mean,
            "heating_gas_per_day": house.heating_gas_per_day,
            "gas_price": house.gas_price,
            "predicted_fraction": predicted,
            "measured_fraction": measured,
            "measured_days": house.measured_days,
            "calibration": factor,
        },
        "rooms": [
            {
                "room_id": r.room_id,
                "name": r.name,
                "day_target": r.day_target,
                "night_target": r.night_target,
                "measured": r.measured,
                "share": shares.get(r.room_id),
                "cooling": r.cooling,
                "estimated_model": not r.cooling,
                "night_drop": night_drop(
                    _delta(r, house.outdoor_mean) or 0.0, _k(r), r.offset, r.night_hours
                )
                if house.outdoor_mean is not None
                else None,
            }
            for r in rooms
        ],
    }
