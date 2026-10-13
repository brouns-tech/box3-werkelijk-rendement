# Werkelijk Rendement — Windows-bèta

Deze bèta reconstrueert box 3-rendement uit ondersteunde financiële documenten.
Verwerking vindt lokaal plaats. De toepassing is gratis en open-source.

1. Pak de volledige ZIP uit in een eigen map.
2. Open `WerkelijkRendement.exe`. Laat de bijbehorende `_internal`-map staan.
3. Het startvenster opent het dashboard in uw standaardbrowser.
4. Kies **Map selecteren** en daarna **Documenten scannen en berekenen**.
5. Bekijk importmeldingen, dekking, berekeningen en de auditexport.
6. Sluit de toepassing via **Afsluiten** in het startvenster. Alleen het sluiten
   van het browsertabblad stopt de toepassing niet.

Python en Poppler hoeft u niet te installeren. De beoogde platformen zijn Windows
10 en 11, 64-bits; beschikbaarheid van een ZIP is geen bewijs dat alle
compatibiliteitscontroles al zijn afgerond. Controleer de release-informatie.

Een tweede keer openen hergebruikt het bestaande dashboard. Bij problemen meldt
het startvenster waar het logbestand staat. Selectie van een map kan worden
geannuleerd. Tijdens import kunt u stoppen na het huidige document; al verwerkte
stukken blijven opgeslagen. De bron-PDF's worden niet gewijzigd.

## Lokale gegevens

De gegevens staan in `%LOCALAPPDATA%\WerkelijkRendement`. Gebruik **Lokale gegevens
openen** in het startvenster om deze map te vinden. De database, instellingen,
selectievoorkeur en logs blijven behouden bij updates of bij het verwijderen van
de uitgepakte toepassing. Ze kunnen financiële en persoonlijke gegevens bevatten.
De database is niet door de toepassing versleuteld.

Maak een back-up door de toepassing af te sluiten en deze gegevensmap te kopiëren.
Verwijder voor een volledige reset de inhoud van deze map nadat de toepassing is
afgesloten. De volgende start maakt een nieuwe lege werkruimte aan. Uw originele
PDF's blijven staan. Gedownloade auditexports staan apart; verwijder die zelf als
u alle afgeleide financiële gegevens wilt verwijderen.

Optionele partnernamen, aliassen en instellingen per instelling kunnen worden
opgegeven in `config.toml` in deze gegevensmap. Zie de repositorydocumentatie.

## Grenzen

Alleen ondersteunde documentlayouts worden verwerkt. Onbekende documenten worden
getoond als niet herkend. Scans zonder tekstlaag worden niet automatisch gelezen.
Volledige import bewijst niet dat al uw bezittingen, schulden of partnerdocumenten
zijn opgenomen. Ontbrekende gegevens kunnen een onbepaald resultaat geven.
Controleer berekeningen en onderliggende stukken voordat u er een fiscale keuze
op baseert. De toepassing is geen aangiftekanaal en is niet verbonden aan de
Belastingdienst.

Een ongetekende bèta kan een Windows-beveiligingsmelding opleveren. Controleer de
herkomst en SHA-256-checksum; zet beveiligingsfuncties niet uit. Gebruik bij twijfel
het bronproject of wacht op een gecontroleerde release.
