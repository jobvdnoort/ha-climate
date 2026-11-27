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
| **Kamers** | Kaart per kamer met huidige temperatuur, doeltemperatuur (met **−/+** in stappen van 0,5 °C, of klik op het getal om een temperatuur in te typen; stelt direct alle vloerverwarmingslussen van de kamer tegelijk in), dagtemperatuur, status (verwarmen / voorverwarmen / nachtverlaging / openhaard actief) en modelbetrouwbaarheid. Heeft de kamer een airco, dan verschijnt een airco-sectie met status, **Uit / Koelen / Boost** en een eigen −/+. Zijn er klepstand-sensoren gekoppeld, dan staat de actuele (gemiddelde en hoogste) klepstand in % op de kaart. Kamers toevoegen, bewerken en verwijderen; nachtverlaging per kamer of voor alle thermostaten schakelen. |
| **Analyses** | Totale gaskosten (variabel + vast) voor vandaag, gisteren en de gekozen periode; variabele besparing; interactieve grafieken (met tooltips) van graaddagen vs. werkelijk en verwacht gasverbruik en de cumulatieve besparing in m³ of €. Per kamer (selector) een **Model status**-kaart: confidence, aantal meetpunten (uit historie / live), 3-stappen voortgang (*Data verzamelen → Kamer leren → Voorspellend regelen*), afkoelsnelheid/warmteverlies, opwarmsnelheid en tijdconstante. Bij de baseline en elk kamermodel staat vanaf welke datum en over hoeveel dagen/meetpunten gerekend wordt. **Vergelijking kamers** rangschikt de ruimtes van minst naar meest zuinig (warmteverlies en stookpercentage) met een label. Gebeurtenissen (nachtverlaging aan/uit, gewijzigde instellingen) staan als kleine vlaggetjes in de grafieken; een wijziging die voor alle kamers tegelijk gebeurde is één regel. Een lijn markeert de **start van de meting**: links de referentieperiode, rechts de meting. De tooltip van de gasgrafiek toont ook de gemiddelde binnen- en doeltemperatuur. **Per uur: wat levert de verlaging op?** toont per uur (van 12:00 de dag ervoor tot 24:00, kies vandaag of een van de 6 dagen ervoor) het werkelijke gasverbruik tegen het verwachte verbruik zonder verlaging: het verwachte dagverbruik, verdeeld over de uren volgens het dagpatroon dat uit de koude dagen van de referentieperiode (zonder verlaging of openhaard, minimaal 7) is geleerd. Zo tellen vaste gewoontes als douchen en de ochtendpiek niet als opwarmkosten. Zijn er te weinig van zulke dagen, dan wordt het gelijkmatig verdeeld (baseline × (stookgrens − buitentemperatuur van dat uur) ÷ 24). Met de verlaagde uren gearceerd. Daaronder de besparing tijdens de verlaging, het extra gas om in de 6 uur daarna op te warmen, het netto resultaat en een oordeel (loont / neutraal / kost meer). De kaart **Besparing meten** toont sinds wanneer er gemeten wordt, de referentie en de besparing totaal / gisteren / vandaag; de startdatum is daar te wijzigen. Knop **Exporteer CSV**. Periode 14 – 365 dagen. Alleen als er een ketel is ingesteld: de sectie **Ketel & efficiëntie** (zie hieronder). |
| **Tips** | Lerend advies met geschatte besparing in € en m³ per maand: nachtverlaging dieper of eerder, overdag lager, kamers die warmer staan dan de rest, kamers die hun doel niet halen of warmer zijn dan ingesteld, hoog warmteverlies, optimum start en ketelpendelen. Gebaseerd op de ingestelde en gemeten temperaturen van de laatste 10 dagen (recorder), het gasverbruik, de geleerde kamermodellen en – na 3 dagen – de werkelijk gemeten besparing (zie *Tips* hieronder). |
| **Schema's** | Per kamer: dagtemperatuur, nachttemperatuur (vast) of verlaging (relatief), eigen tijden of de algemene, "op temperatuur om"-tijd en Optimum Start, met de geplande starttijd. Of kies **Comfortblokken**: een of meer blokken per dag (bijv. badkamer 06:30–07:30 en 17:00–21:00) waarin de kamer op dagtemperatuur staat; daarbuiten verlaagd. |
| **Instellingen** | In vier stappen: meters, gasprijs, nachtverlaging en *besparing meten vanaf*. Inklapbaar: dynamische gasprijs, openhaard, **Ketel / OpenTherm** en *geavanceerd* (stookgrens, referentieperiode, graaddagcorrectie). |

Wijzigingen vereisen een beheerdersaccount; andere gebruikers zien het paneel alleen-lezen. Het paneel praat met de integratie via een eigen WebSocket API (`ha_climate/state`, `ha_climate/history`, `ha_climate/room/save`, …).

## Configuratie (volledig via de UI)

Bij het toevoegen kies je:

| Instelling | Toelichting |
|---|---|
| Buitentemperatuur-sensor | `sensor` met `device_class: temperature` en `state_class: measurement` |
| Gasverbruik-sensor | Gasmeterstand in m³ (`device_class: gas`, `state_class: total_increasing`) |
| Gasprijs | Vast bedrag in €/m³ en/of een entiteit (sensor/input_number); de entiteit gaat voor |
| Vaste leveringskosten | Optioneel (vastrecht/netbeheer), standaard 0,00, **per maand** (standaard) of per dag. Een maandbedrag wordt omgerekend naar dagkosten (`maandbedrag / 30,4375`). Telt mee in de totale gaskosten, niet in de besparing |
| Startdatum besparing | Optioneel: vanaf deze dag wordt de besparing (cumulatief vanaf 0) gemeten |
| Graaddagen corrigeren voor comforttemperatuur | Optioneel: stookgrens + (gemiddelde comforttemperatuur zonder nachtverlaging − referentie) per dag. De referentie (standaard 20,0 °C) is de temperatuur waarop het huis in de baselineperiode werd verwarmd |
| Stookgrens | Standaard 18,0 °C |
| Baseline-periode | Aantal dagen voor de baseline; 0 (standaard) = alles vanaf de eerste dag dat beide sensoren data hebben |
| Nachtverlaging | Start 22:00, einde 06:30, verlaging −2,0 °C |

Alles hieronder kan ook in het zijbalk-paneel. Via **Configureren** (options flow) kun je daarna:

* **Ruimtes toevoegen/bewerken/verwijderen** – elke ruimte bevat één of meer `climate`-entiteiten (vloerverwarmingslussen) en kan de algemene nachtverlaging gebruiken of eigen tijden/verlaging hebben, plus optioneel een dag- en nachttemperatuur, "op temperatuur om" en Optimum Start.
* **Openhaard** – kies de thermostaat van de openhaard-ruimte, optioneel een losse temperatuursensor, en de drempel (standaard +0,5 °C).
* Sensoren, prijs, stookgrens en standaard-nachtverlaging wijzigen.

## Ketel (OpenTherm) en klepstanden – optioneel

Beide uitbreidingen zijn volledig optioneel: zonder ketel- of klepstand-entiteiten verandert er niets aan de werking of het paneel.

**Ketel / OpenTherm** (Instellingen → *Ketel / OpenTherm (optioneel)*), bijvoorbeeld via OpenTherm Gateway of ems-esp:

| Instelling | Domein | Voorbeeld |
|---|---|---|
| Brander / vlamstatus | `binary_sensor` | `cv_vlam_status` |
| Warmtevraag | `binary_sensor` | `ot_heat_request` |
| Tapwater / warm water status | `binary_sensor` | `cv_warm_water_status` |
| Modulatie (%) | `sensor` | `cv_degree_of_modulation` |
| Werkelijke / gevraagde aanvoertemperatuur (°C) | `sensor` | `cv_h1_water_temperatuur` / `cv_h1_flow_setpoint_value` |
| Waterdruk (bar) en foutcode | `sensor` | `cv_waterdruk` / `cv_error_code` |
| Starts vandaag, branduren vandaag, gem. looptijd | `sensor` | optioneel; anders berekent HA Climate deze zelf uit de vlamstatus |

Op het tabblad **Analyses** verschijnt dan **Ketel & efficiëntie** met:

* een statusbalk: brander (verwarming/tapwater, lopende run), warmtevraag, modulatie, aanvoer vs. gevraagd, waterdruk (rood onder 1,2 bar) en foutcode;
* KPI's: branderstarts per dag, branduren, gemiddelde brandtijd per start (branduren ÷ starts, inclusief de lopende run; waarschuwing **pendelen** bij gemiddeld < 10 min met ≥ 3 starts; runs < 10 min tellen als korte run, en bij ≥ 6 korte runs die minstens de helft van de afgeronde runs zijn verschijnt **Veel korte runs**) en gemiddelde aanvoertemperatuur/modulatie tijdens branden;
* **tapwater vs. verwarming** (minuten en %) voor vandaag en de gekozen periode – opgeslagen per dag en meegenomen in de CSV-export (`ketel_*`-kolommen);
* een grafiek van de laatste 24 uur (uit de recorder): aanvoertemperatuur, gevraagde aanvoer, modulatie, de hoogste kamer-klepstand en de periodes dat de brander aan was;
* een grafiek van starts en branduren per dag.

Starts worden geteld bij elke wisseling van de vlamstatus (niet alleen per minuut); branduren, tapwater- en verwarmingstijd per minuut. Tellers van de ketel zelf (indien ingesteld) gaan voor.

**Klepstand / stelgraad per kamer** (kamer toevoegen/bewerken): koppel één of meer `sensor`-entiteiten (0–100 %) van de vloerverwarmingsactoren, bijv. KNX. Dan

* gebruikt het thermische model de gemiddelde klepopening als verwarmingsintensiteit (in plaats van aan/uit uit `hvac_action`), ook bij het terugrekenen uit de recorder-historie – dat geeft een nauwkeurigere opwarmsnelheid;
* is het **stookpercentage** in de kamervergelijking de gemiddelde klepopening;
* staat de actuele klepstand op de kamerkaart.

## Entiteiten

| Entiteit | Beschrijving |
|---|---|
| `sensor` Graaddagen vandaag | Opgebouwde graaddagen tot nu (attribuut: prognose voor de hele dag) |
| `sensor` Graaddagen gisteren | |
| `sensor` Baseline gas per graaddag | m³/graaddag, met attributen over gebruikte en uitgesloten dagen |
| `sensor` Verwacht gasverbruik vandaag/gisteren | baseline × graaddagen |
| `sensor` Werkelijk gasverbruik vandaag/gisteren | uit de statistieken van de gasmeter |
| `sensor` Gaskosten vandaag/gisteren | variabel verbruik × gasprijs + vaste leveringskosten per dag |
| `sensor` Bespaard gas vandaag/gisteren/totaal | verwacht − werkelijk (m³); het totaal wordt bewaard en na een herstart hersteld (`RestoreEntity`) |
| `sensor` Besparing vandaag/gisteren/totaal | idem in €; zonder ingestelde prijs wordt € 1,40/m³ gebruikt (attribuut `prijsbron`) |
| `sensor` Afkoelsnelheid / Opwarmsnelheid *kamer* | geleerde snelheid in °C/uur bij de huidige binnen-buiten ΔT |
| `sensor` Betrouwbaarheid model *kamer* | 0–100 % |
| `sensor` Starttijd verwarming *kamer* | geplande Optimum Start (alleen als Optimum Start aan staat) |
| `binary_sensor` Openhaard actief | alleen als een openhaard-thermostaat is gekozen |
| `switch` Alle thermostaten nachtverlaging | hoofdschakelaar (bij bestaande installaties blijft de entity-id `switch.ha_climate_night_setback`) |
| `switch` Nachtverlaging *ruimte* | per ruimte, bijv. "Nachtverlaging Woonkamer en keuken" |
| `button` Baseline herberekenen | leest de LTS opnieuw uit |

Service: `ha_climate.recalculate_baseline` (optioneel `config_entry_id`, geeft het resultaat terug als response). Deze voert een volledige herberekening uit: gas-baseline én thermische backfill (zie hieronder).

## Hoe het werkt

**Permanente opslag.** Naast de recorder houdt HA Climate een eigen, permanente opslag bij (`.storage/ha_climate.history.<entry>`): alle dagwaarden (gemiddelde buitentemperatuur en gasverbruik) en álle thermische meetblokken per kamer. Daardoor gaat er niets verloren als de recorder na 10 dagen (standaard `purge_keep_days`) states opruimt, en blijft het model over maanden en seizoenen doorleren. Meetblokken liggen op een vast raster van 2 uur en worden op hun starttijd gededupliceerd: herberekenen of opnieuw backfillen maakt nooit dubbele meetpunten.

**Baseline (Long-Term Statistics).** Bij een volledige herberekening (knop, service of paneel) bepaalt HA Climate eerst de vroegste dag waarop zowel de buitentemperatuur- als de gassensor langetermijnstatistieken hebben (de overlap), leest alle dagen vanaf die dag in en slaat ze permanent op. Dagen waarop een van beide sensoren ontbreekt worden overgeslagen. Bij het opstarten en elke nacht om 00:20 worden alleen de laatste dagen bijgewerkt. De baseline is `Σ gas / Σ graaddagen` over alle bruikbare dagen vanaf de overlap (of de laatste *N* dagen als een baseline-periode is ingesteld). Uitgesloten worden: dagen zonder volledige data, dagen met < 1 graaddag (vooral warm water), dagen waarop de openhaard ≥ 30 minuten brandde en dagen waarop de nachtverlaging actief was (de baseline moet het verbruik *zonder* besparing weergeven). Als er te weinig schone dagen overblijven (< 7) blijft de laatst geldige baseline staan.

**Openhaard-detectie.** De openhaard geldt als actief wanneer de vloerverwarming in die ruimte niet verwarmt (`hvac_action` ≠ `heating`) en de temperatuur ten minste de drempel boven de doeltemperatuur ligt, óf binnen een uur ten minste de drempel is gestegen (alleen als de vloerverwarming dat uur niet heeft gestookt, om naverwarming van de vloer niet mee te tellen). Tijdens de nachtverlaging wordt met de oorspronkelijke comforttemperatuur vergeleken. Uitschakelen gebeurt met hysterese (halve drempel). Detectie werkt vanaf het moment van installatie; oudere historie kan niet met terugwerkende kracht worden gecorrigeerd.

**Nachtverlaging.** Elke minuut wordt per ruimte gecontroleerd of de verlaging actief moet zijn. Bij de start wordt de huidige doeltemperatuur van elke lus opgeslagen en ingesteld op de vaste nachttemperatuur, of met de verlaging verminderd (afgerond op de stapgrootte en niet onder `min_temp`). In de ochtend wordt de dagtemperatuur (of anders de oorspronkelijke temperatuur) hersteld – behalve als iemand de thermostaat 's nachts handmatig heeft aangepast. Een ingestelde dagtemperatuur wordt bij opslaan direct toegepast als de kamer niet in nachtverlaging staat.

**Zelflerend thermisch model.** Elke minuut worden per kamer de gemiddelde binnentemperatuur van de lussen, de buitentemperatuur en of de vloerverwarming verwarmt (`hvac_action`) vastgelegd. Elk blok van 2 uur levert één meetmoment op: de temperatuurhelling, de inschakelduur (duty cycle, zodat ook pulserende thermostaten werken) en het gemiddelde ΔT binnen–buiten. Met kleinste kwadraten wordt het model `dT/dt = h · duty − k · (T_binnen − T_buiten)` gefit over de laatste ~25 dagen:

* **Afkoelsnelheid** = `k × ΔT` (°C/uur), met `k` de afkoelcoëfficiënt,
* **Opwarmsnelheid** = `h − k × ΔT` (°C/uur) bij volle verwarming,
* **Betrouwbaarheid** (0–100 %) groeit met het aantal meetmomenten (vol na 60) en daalt bij een grote standaardfout van de schatting. De algemene score is de laagste van afkoelen en opwarmen.

Meetmomenten met gaten, onbekende `hvac_action` of een brandende openhaard worden overgeslagen. Alle meetpunten worden permanent bewaard; de fit gebruikt het meest recente seizoen (90 dagen, minimaal de laatste 300 meetpunten). De **tijdconstante** τ = 1/k (uur) geeft aan hoe traag de kamer reageert. Het model kan per kamer worden gereset in het paneel.

**Backfill uit recorder-historie.** Bij een volledige herberekening en wanneer een kamer voor het eerst wordt geladen (bijv. net toegevoegd), leest HA Climate de recorder-historie van de `climate`-entiteiten (`current_temperature`, `temperature`, `hvac_action`) en de buitentemperatuur, vanaf het vroegste moment waarop al deze entiteiten historie hebben. Uit die historie worden direct meetblokken berekend, op hetzelfde 2-uursraster als de live metingen, zodat een kamer niet op 0 % begint. Periodes waarin de openhaard actief was (historie van `binary_sensor` *Openhaard actief*) worden overgeslagen.

**Model status.** (1) *Data verzamelen* tot er een dag aan meetpunten is en de confidence ≥ 20 % is, (2) *Kamer leren* tot 50 %, (3) *Voorspellend regelen*: vanaf daar gebruikt Optimum Start het geleerde model in plaats van de veilige fallback.

**Optimum Start.** Met "op temperatuur om" (bijv. 07:00) en Optimum Start aan berekent HA Climate elke minuut hoe lang het opwarmen duurt van de huidige binnentemperatuur naar de dagtemperatuur, rekening houdend met de buitentemperatuur (oplossing van bovenstaande vergelijking), plus 15 minuten marge. Op dat moment eindigt de nachtverlaging. Zolang de betrouwbaarheid onder 50 % ligt, wordt een **veilige fallback** gebruikt: 0,5 °C per uur, of het model als dat een vroegere start geeft. De voorverwarmtijd is begrensd op 6 uur en na het herstel wordt in dezelfde nacht niet opnieuw verlaagd. De status wordt persistent opgeslagen, zodat een herstart van Home Assistant niets verstoort. Uitschakelen van een schakelaar, verwijderen van een ruimte of van de integratie herstelt de lussen direct.

**Comfortblokken.** In plaats van één nachtvenster kun je per kamer tot 6 comfortblokken per dag instellen. Buiten de blokken wordt de kamer verlaagd (nachttemperatuur of verlaging), precies zoals bij de nachtverlaging; elk gat tussen twee blokken is een eigen verlagingsvenster. Met Optimum Start begint het opwarmen vóór elk blok op het berekende moment (geleerd model + buitentemperatuur, anders de veilige fallback). Blokken mogen over middernacht lopen; overlappende blokken worden samengevoegd. Wijzigingen worden net als de nachtverlaging gelogd en als aparte periode gemeten op Analyses.

**Airco's.** Per kamer kun je optioneel airco's (`climate`-entiteiten) koppelen. Die staan volledig los van de vloerverwarming: ze doen niet mee met nachtverlaging, dagschema's of Optimum Start. Zolang een airco verwarmt of koelt (`hvac_action` `heating`/`cooling`, of aan zonder `hvac_action`), wordt die periode uitgesloten van het thermische vloerverwarmingsmodel, ook bij de backfill uit de recorder-historie. *Boost* zet de airco op verwarmen naar de dagtemperatuur van de kamer + 0,5 °C; *Koelen* zet hem op koelen (standaard 22 °C als er nog geen doel is).

**Besparing meten vanaf.** Kies de dag waarop je met besparen begon (bijv. de eerste nacht met nachtverlaging). De baseline wordt alleen uit de dagen *vóór* die datum geleerd en ligt daarmee vast; vanaf die dag start de besparing op 0. Een andere startdatum leert de baseline opnieuw uit de dagen daarvóór. (Het vroegere "bevriezen" is hierdoor vervallen.)

**Tips.** Een kamer verliest warmte in verhouding tot het verschil tussen binnen en buiten, dus alles wat een kamer een tijd koeler houdt bespaart `graad-uren koeler ÷ (24 h × ΔT)` van het gas voor die kamer. Voor de nachtverlaging wordt met het geleerde model per kamer (afkoelcoëfficiënt k en opwarmsnelheid) berekend hoe ver de kamer echt afkoelt en hoe lang het weer opwarmen duurt; zonder model wordt een gemiddelde vloerverwarmingswoning aangenomen. Het gas per kamer wordt verdeeld naar aantal lussen × ΔT. Het verwarmingsgas is baseline × gemiddelde graaddagen van de laatste 10 dagen. Na 3 volledige meetdagen sinds de startdatum worden alle schattingen bijgesteld met de verhouding gemeten / voorspelde besparing (na 14 dagen volledig), zodat het advies leert van de werkelijkheid. WebSocket: `ha_climate/advice`.

**Logboek per instelling.** Elke wijziging van de nachtverlaging (tijden, verlaging, aan/uit, per kamer of voor alle thermostaten) start een nieuwe periode; een wijziging na 12:00 telt vanaf de volgende dag. Per periode worden verbruikt en verwacht gas over volledige dagen (zonder openhaard) bijgehouden, zichtbaar op Analyses en Tips. Na 3 dagen beoordeelt HA Climate de huidige instelling: werkt hij, levert hij niets op, of deed een eerdere instelling het duidelijk beter – dan verschijnt een tip met een knop **Terugzetten**. Per periode wordt ook onthouden wat het model voorspelde, zodat de kalibratie over wijzigingen heen doorleert.

**Openhaard na handmatig lager zetten.** Wordt de doeltemperatuur verlaagd, dan staat de kamer een tijd boven het nieuwe doel; dat telt niet meer als openhaard. Tot de kamer is afgekoeld telt alleen een echte temperatuurstijging. Een verkeerd gedetecteerde dag kun je op Analyses wissen (*klopt niet*).

**Binnentemperatuur.** Elke minuut wordt de gemiddelde gemeten en ingestelde binnentemperatuur over de kamers bijgehouden en per dag permanent opgeslagen. Daarnaast wordt de **comforttemperatuur** bijgehouden: de dagtemperatuur van elke kamer, ook tijdens de nachtverlaging (dan de oorspronkelijke temperatuur van vóór de verlaging). Met de optionele correctie wordt de stookgrens per dag verschoven met het verschil tussen de gemiddelde comforttemperatuur en de **referentie-comforttemperatuur** (de vaste 18 °C-stookgrens gaat uit van ~20 °C binnen). Zet je de kamers warmer dan in de baselineperiode, dan stijgt het verwachte verbruik mee; de nachtverlaging telt niet mee in de correctie en blijft dus als besparing zichtbaar. Dagen zonder bekende comforttemperatuur (bijv. vóór installatie, dus vaak de baselineperiode) tellen als de referentie, zodat baseline en metingen dezelfde regel gebruiken. Vul daarom als referentie de temperatuur in die je in de baselineperiode aanhield.

**Onzuinigste ruimte.** Per kamer worden het genormaliseerde warmteverlies (de geleerde afkoelcoëfficiënt k, °C/uur per °C ΔT) en het stookpercentage van de afgelopen 7 dagen (gemiddelde inschakelduur van de meetblokken) gecombineerd tot een energiescore, relatief tot de slechtste kamer. Labels: *Hoog warmteverlies* (k ≥ 0,06), *Stookt veel* (≥ 50 % van de tijd), *Gemiddeld* (k ≥ 0,035 of ≥ 25 %) of *Zuinig*.

**Wijzigingslogboek.** Nachtverlaging aan/uit (globaal of per kamer), gewijzigde nachtinstellingen (tijden, verlaging, nachttemperatuur, optimum start – ongeacht of dat via het paneel of de options flow gebeurt) worden permanent opgeslagen en in de grafieken en de export getoond.

**CSV-export.** *Exporteer CSV* downloadt alle opgeslagen dagen (UTF-8, komma-gescheiden, punt als decimaalteken) met: datum, gemiddelde buiten-, binnen- en doeltemperatuur, stookgrens, graaddagen, werkelijk en verwacht gasverbruik, besparing (m³ en €), variabele, vaste en totale kosten, openhaard-minuten, nachtverlaging (ja/nee) en de gebeurtenissen van die dag. Met een ingestelde ketel komen daar per dag bij: starts, branduren, gemiddelde looptijd, korte runs, tapwater- en verwarmingsminuten, tapwater-% en gemiddelde aanvoertemperatuur en modulatie.

**Besparing totaal** telt de besparing (verwacht − werkelijk) van alle afgeronde dagen sinds de startdatum van de besparing (of anders de installatie) plus vandaag tot nu. Gemiste dagen worden bij het herberekenen van de baseline aangevuld uit de statistieken. De baseline krijgt al vanaf één bruikbare dag een waarde (zodat sensoren niet op "onbekend" blijven staan) en is vanaf 7 dagen "betrouwbaar". Negatieve dagverbruiken (meterwissel of -reset) worden genegeerd.

## Ontwikkeling & tests

```bash
pip install pytest
pytest
```

De unit tests in `tests/` testen de pure rekenlogica (graaddagen, baseline, openhaard, nachtverlaging, thermisch model, Optimum Start, ketel-tracking en klepstanden) zonder Home Assistant. End-to-end tests met een echte Home Assistant-testinstantie (config flow, opties, paneel-registratie, WebSocket API, nachtverlaging, Optimum Start en het herstellen van de totale besparing) staan in `tests_integration/`:

```bash
pip install -r requirements_test.txt
pytest tests_integration
```
