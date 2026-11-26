# HA Climate – Graaddagen, gasbesparing & nachtverlaging

Home Assistant custom integration (HACS) die

* dagelijks **graaddagen** berekent (`max(0, stookgrens − gemiddelde buitentemperatuur)`),
* uit de **Long-Term Statistics** van de recorder een **gas-baseline** (m³ per graaddag) bepaalt,
* een **openhaard** automatisch detecteert en die dagen uitsluit van de baseline,
* een schakelbare **nachtverlaging** voor vloerverwarming uitvoert (per ruimte, meerdere lussen),
* per kamer een **zelflerend thermisch model** bijhoudt (afkoel- en opwarmsnelheid + betrouwbaarheid),
* met **Optimum Start** de verwarming precies op tijd laat starten,
* en laat zien hoeveel gas (m³ en €) je bespaart t.o.v. het verwachte verbruik,
* met een eigen **zijbalk-paneel** (Kamers, Analyses, Schema's, Instellingen).

## Installatie via HACS

1. HACS → ⋮ → **Custom repositories** → voeg `https://github.com/jobvdnoort/ha-climate` toe als type **Integration**.
2. Zoek **HA Climate** in HACS en klik **Download**.
3. Herstart Home Assistant.
4. **Instellingen → Apparaten & diensten → Integratie toevoegen → HA Climate**.

Handmatig: kopieer `custom_components/ha_climate` naar `<config>/custom_components/` en herstart.

Vereist Home Assistant 2025.2 of nieuwer met de `recorder` actief.

## Zijbalk-paneel

Na installatie verschijnt **HA Climate** (thermostaat-icoon) in de linkerzijbalk. Er is geen YAML nodig: de integratie serveert de frontend zelf vanuit `custom_components/ha_climate/frontend/` en registreert het paneel automatisch. Het paneel volgt het licht/donker-thema van Home Assistant en werkt ook op mobiel.

| Tabblad | Inhoud |
|---|---|
| **Kamers** | Kaart per kamer met huidige temperatuur, doeltemperatuur, dagtemperatuur, status (verwarmen / voorverwarmen / nachtverlaging / openhaard actief) en modelbetrouwbaarheid. Kamers toevoegen, bewerken en verwijderen; nachtverlaging per kamer of voor alle thermostaten schakelen. |
| **Analyses** | Interactieve grafieken (met tooltips): graaddagen vs. werkelijk en verwacht gasverbruik per dag, cumulatieve gasbesparing in m³ of €, en per kamer afkoel-/opwarmsnelheid met betrouwbaarheid. Periode 14 – 365 dagen. |
| **Schema's** | Per kamer: dagtemperatuur, nachttemperatuur (vast) of verlaging (relatief), eigen tijden of de algemene, "op temperatuur om"-tijd en Optimum Start, met de geplande starttijd. |
| **Instellingen** | Buitentemperatuur- en gassensor, gasprijs (vast of entiteit), stookgrens, historie, algemene nachtverlaging en openhaard. |

Wijzigingen vereisen een beheerdersaccount; andere gebruikers zien het paneel alleen-lezen. Het paneel praat met de integratie via een eigen WebSocket API (`ha_climate/state`, `ha_climate/history`, `ha_climate/room/save`, …).

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

Alles hieronder kan ook in het zijbalk-paneel. Via **Configureren** (options flow) kun je daarna:

* **Ruimtes toevoegen/bewerken/verwijderen** – elke ruimte bevat één of meer `climate`-entiteiten (vloerverwarmingslussen) en kan de algemene nachtverlaging gebruiken of eigen tijden/verlaging hebben, plus optioneel een dag- en nachttemperatuur, "op temperatuur om" en Optimum Start.
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
| `sensor` Bespaard gas vandaag/gisteren/totaal | verwacht − werkelijk (m³); het totaal wordt bewaard en na een herstart hersteld (`RestoreEntity`) |
| `sensor` Besparing vandaag/gisteren/totaal | idem in €; zonder ingestelde prijs wordt € 1,40/m³ gebruikt (attribuut `prijsbron`) |
| `sensor` Afkoelsnelheid / Opwarmsnelheid *kamer* | geleerde snelheid in °C/uur bij de huidige binnen-buiten ΔT |
| `sensor` Betrouwbaarheid model *kamer* | 0–100 % |
| `sensor` Starttijd verwarming *kamer* | geplande Optimum Start (alleen als Optimum Start aan staat) |
| `binary_sensor` Openhaard actief | alleen als een openhaard-thermostaat is gekozen |
| `switch` Alle thermostaten nachtverlaging | hoofdschakelaar (bij bestaande installaties blijft de entity-id `switch.ha_climate_night_setback`) |
| `switch` Nachtverlaging *ruimte* | per ruimte, bijv. "Nachtverlaging Woonkamer en keuken" |
| `button` Baseline herberekenen | leest de LTS opnieuw uit |

Service: `ha_climate.recalculate_baseline` (optioneel `config_entry_id`, geeft het resultaat terug als response).

## Hoe het werkt

**Baseline.** Bij het opstarten, elke nacht om 00:20 en via knop/service worden de dagstatistieken (gemiddelde buitentemperatuur en gasverbruik per dag) uit de recorder gelezen. De baseline is `Σ gas / Σ graaddagen` over alle bruikbare dagen. Uitgesloten worden: dagen zonder volledige data, dagen met < 1 graaddag (vooral warm water), dagen waarop de openhaard ≥ 30 minuten brandde en dagen waarop de nachtverlaging actief was (de baseline moet het verbruik *zonder* besparing weergeven). Als er te weinig schone dagen overblijven (< 7) blijft de laatst geldige baseline staan.

**Openhaard-detectie.** De openhaard geldt als actief wanneer de vloerverwarming in die ruimte niet verwarmt (`hvac_action` ≠ `heating`) en de temperatuur ten minste de drempel boven de doeltemperatuur ligt, óf binnen een uur ten minste de drempel is gestegen (alleen als de vloerverwarming dat uur niet heeft gestookt, om naverwarming van de vloer niet mee te tellen). Tijdens de nachtverlaging wordt met de oorspronkelijke comforttemperatuur vergeleken. Uitschakelen gebeurt met hysterese (halve drempel). Detectie werkt vanaf het moment van installatie; oudere historie kan niet met terugwerkende kracht worden gecorrigeerd.

**Nachtverlaging.** Elke minuut wordt per ruimte gecontroleerd of de verlaging actief moet zijn. Bij de start wordt de huidige doeltemperatuur van elke lus opgeslagen en ingesteld op de vaste nachttemperatuur, of met de verlaging verminderd (afgerond op de stapgrootte en niet onder `min_temp`). In de ochtend wordt de dagtemperatuur (of anders de oorspronkelijke temperatuur) hersteld – behalve als iemand de thermostaat 's nachts handmatig heeft aangepast. Een ingestelde dagtemperatuur wordt bij opslaan direct toegepast als de kamer niet in nachtverlaging staat.

**Zelflerend thermisch model.** Elke minuut worden per kamer de gemiddelde binnentemperatuur van de lussen, de buitentemperatuur en of de vloerverwarming verwarmt (`hvac_action`) vastgelegd. Elk blok van 2 uur levert één meetmoment op: de temperatuurhelling, de inschakelduur (duty cycle, zodat ook pulserende thermostaten werken) en het gemiddelde ΔT binnen–buiten. Met kleinste kwadraten wordt het model `dT/dt = h · duty − k · (T_binnen − T_buiten)` gefit over de laatste ~25 dagen:

* **Afkoelsnelheid** = `k × ΔT` (°C/uur), met `k` de afkoelcoëfficiënt,
* **Opwarmsnelheid** = `h − k × ΔT` (°C/uur) bij volle verwarming,
* **Betrouwbaarheid** (0–100 %) groeit met het aantal meetmomenten (vol na 60) en daalt bij een grote standaardfout van de schatting. De algemene score is de laagste van afkoelen en opwarmen.

Meetmomenten met gaten, onbekende `hvac_action` of een brandende openhaard worden overgeslagen. Het model wordt bewaard en kan per kamer worden gereset in het paneel.

**Optimum Start.** Met "op temperatuur om" (bijv. 07:00) en Optimum Start aan berekent HA Climate elke minuut hoe lang het opwarmen duurt van de huidige binnentemperatuur naar de dagtemperatuur, rekening houdend met de buitentemperatuur (oplossing van bovenstaande vergelijking), plus 15 minuten marge. Op dat moment eindigt de nachtverlaging. Zolang de betrouwbaarheid onder 50 % ligt, wordt een **veilige fallback** gebruikt: 0,5 °C per uur, of het model als dat een vroegere start geeft. De voorverwarmtijd is begrensd op 6 uur en na het herstel wordt in dezelfde nacht niet opnieuw verlaagd. De status wordt persistent opgeslagen, zodat een herstart van Home Assistant niets verstoort. Uitschakelen van een schakelaar, verwijderen van een ruimte of van de integratie herstelt de lussen direct.

**Besparing totaal** telt de besparing (verwacht − werkelijk) van alle afgeronde dagen sinds de installatie plus vandaag tot nu. Gemiste dagen worden bij het herberekenen van de baseline aangevuld uit de statistieken. De baseline krijgt al vanaf één bruikbare dag een waarde (zodat sensoren niet op "onbekend" blijven staan) en is vanaf 7 dagen "betrouwbaar". Negatieve dagverbruiken (meterwissel of -reset) worden genegeerd.

## Ontwikkeling & tests

```bash
pip install pytest
pytest
```

De unit tests in `tests/` testen de pure rekenlogica (graaddagen, baseline, openhaard, nachtverlaging, thermisch model en Optimum Start) zonder Home Assistant. End-to-end tests met een echte Home Assistant-testinstantie (config flow, opties, paneel-registratie, WebSocket API, nachtverlaging, Optimum Start en het herstellen van de totale besparing) staan in `tests_integration/`:

```bash
pip install -r requirements_test.txt
pytest tests_integration
```
