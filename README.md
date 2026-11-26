# HA Climate – Graaddagen, gasbesparing & nachtverlaging

Home Assistant custom integration (HACS) die

* dagelijks **graaddagen** berekent (`max(0, stookgrens − gemiddelde buitentemperatuur)`),
* uit de **Long-Term Statistics** van de recorder een **gas-baseline** (m³ per graaddag) bepaalt,
* een **openhaard** automatisch detecteert en die dagen uitsluit van de baseline,
* een schakelbare **nachtverlaging** voor vloerverwarming uitvoert (per ruimte, meerdere lussen),
* en laat zien hoeveel gas (m³ en €) je bespaart t.o.v. het verwachte verbruik.

## Installatie via HACS

1. HACS → ⋮ → **Custom repositories** → voeg `https://github.com/jobvdnoort/ha-climate` toe als type **Integration**.
2. Zoek **HA Climate** in HACS en klik **Download**.
3. Herstart Home Assistant.
4. **Instellingen → Apparaten & diensten → Integratie toevoegen → HA Climate**.

Handmatig: kopieer `custom_components/ha_climate` naar `<config>/custom_components/` en herstart.

Vereist Home Assistant 2025.2 of nieuwer met de `recorder` actief.

## Configuratie (volledig via de UI)

Bij het toevoegen kies je:

| Instelling | Toelichting |
|---|---|
| Buitentemperatuur-sensor | `sensor` met `device_class: temperature` en `state_class: measurement` |
| Gasverbruik-sensor | Gasmeterstand in m³ (`device_class: gas`, `state_class: total_increasing`) |
| Gasprijs | Vast bedrag in €/m³ en/of een entiteit (sensor/input_number); de entiteit gaat voor |
| Stookgrens | Standaard 18,0 °C |
| Historie voor baseline | Aantal dagen LTS dat wordt gebruikt (standaard 365) |
| Nachtverlaging | Start 22:00, einde 06:30, verlaging −2,0 °C |

Via **Configureren** (options flow) kun je daarna:

* **Ruimtes toevoegen/bewerken/verwijderen** – elke ruimte bevat één of meer `climate`-entiteiten (vloerverwarmingslussen) en kan de algemene nachtverlaging gebruiken of eigen tijden/verlaging hebben.
* **Openhaard** – kies de thermostaat van de openhaard-ruimte, optioneel een losse temperatuursensor, en de drempel (standaard +0,5 °C).
* Sensoren, prijs, stookgrens en standaard-nachtverlaging wijzigen.

## Entiteiten

| Entiteit | Beschrijving |
|---|---|
| `sensor` Graaddagen vandaag | Opgebouwde graaddagen tot nu (attribuut: prognose voor de hele dag) |
| `sensor` Graaddagen gisteren | |
| `sensor` Baseline gas per graaddag | m³/graaddag, met attributen over gebruikte en uitgesloten dagen |
| `sensor` Verwacht gasverbruik vandaag/gisteren | baseline × graaddagen |
| `sensor` Werkelijk gasverbruik vandaag/gisteren | uit de statistieken van de gasmeter |
| `sensor` Bespaard gas vandaag/gisteren/totaal | verwacht − werkelijk (m³) |
| `sensor` Besparing vandaag/gisteren/totaal | idem in € (als een gasprijs is ingesteld) |
| `binary_sensor` Openhaard actief | alleen als een openhaard-thermostaat is gekozen |
| `switch` Nachtverlaging | hoofdschakelaar |
| `switch` Nachtverlaging *ruimte* | per ruimte |
| `button` Baseline herberekenen | leest de LTS opnieuw uit |

Service: `ha_climate.recalculate_baseline` (optioneel `config_entry_id`, geeft het resultaat terug als response).

## Hoe het werkt

**Baseline.** Bij het opstarten, elke nacht om 00:20 en via knop/service worden de dagstatistieken (gemiddelde buitentemperatuur en gasverbruik per dag) uit de recorder gelezen. De baseline is `Σ gas / Σ graaddagen` over alle bruikbare dagen. Uitgesloten worden: dagen zonder volledige data, dagen met < 1 graaddag (vooral warm water), dagen waarop de openhaard ≥ 30 minuten brandde en dagen waarop de nachtverlaging actief was (de baseline moet het verbruik *zonder* besparing weergeven). Als er te weinig schone dagen overblijven (< 7) blijft de laatst geldige baseline staan.

**Openhaard-detectie.** De openhaard geldt als actief wanneer de vloerverwarming in die ruimte niet verwarmt (`hvac_action` ≠ `heating`) en de temperatuur ten minste de drempel boven de doeltemperatuur ligt, óf binnen een uur ten minste de drempel is gestegen (alleen als de vloerverwarming dat uur niet heeft gestookt, om naverwarming van de vloer niet mee te tellen). Tijdens de nachtverlaging wordt met de oorspronkelijke comforttemperatuur vergeleken. Uitschakelen gebeurt met hysterese (halve drempel). Detectie werkt vanaf het moment van installatie; oudere historie kan niet met terugwerkende kracht worden gecorrigeerd.

**Nachtverlaging.** Elke minuut wordt per ruimte gecontroleerd of de verlaging actief moet zijn. Bij de start wordt de huidige doeltemperatuur van elke lus opgeslagen en met de verlaging verminderd (afgerond op de stapgrootte en niet onder `min_temp`). In de ochtend wordt de oorspronkelijke temperatuur hersteld – behalve als iemand de thermostaat 's nachts handmatig heeft aangepast. De status wordt persistent opgeslagen, zodat een herstart van Home Assistant niets verstoort. Uitschakelen van een schakelaar, verwijderen van een ruimte of van de integratie herstelt de lussen direct.

**Besparing totaal** telt de besparing van afgeronde dagen waarop de nachtverlaging actief was.

## Ontwikkeling & tests

```bash
pip install pytest
pytest
```

De unit tests in `tests/` testen de pure rekenlogica (graaddagen, baseline, openhaard, nachtverlaging) zonder Home Assistant. Een end-to-end test met een echte Home Assistant-testinstantie staat in `tests_integration/`:

```bash
pip install -r requirements_test.txt
pytest tests_integration
```
