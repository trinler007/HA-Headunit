# HA Headunit

Home-Assistant-Integration für eine Linux-Headunit mit [LIVI](https://github.com/f-io/LIVI) (Android Auto / CarPlay). Home Assistant schickt Fahrzeugdaten aktiv an die Telemetrie-API von LIVI. LIVI reicht sie an Android Auto und CarPlay weiter, so wie es in einem Serienfahrzeug OBD2 bzw. CAN tun würde. Optional steuert die Integration die Kameraansicht [camview](https://github.com/trinler007/NX01-Headunit/tree/main/services/camview).

## Funktionen

- Ereignisgesteuert: Änderungen der zugeordneten Entitäten gehen sofort an LIVI, innerhalb von 200 ms zu einem Push gebündelt
- Alle 30 s der vollständige Stand – hält LIVI nach einem Neustart aktuell und prüft die Erreichbarkeit
- Einheiten werden umgerechnet (km/h, m/s, mph, kn; °F, K; m, mi; mV)
- Zuordnung in der Oberfläche: Geschwindigkeit, Rückwärtsgang, Gang, Feststellbremse, Licht, Fernlicht, Warnblinker, Nachtmodus, Tank, Reichweite, Kilometerstand, Außen-/Kühlwassertemperatur, Batteriespannung, Drehzahl
- GPS aus einem `device_tracker` (z. B. HA-Teltonika), optional Höhe, Geschwindigkeit, Kurs, Genauigkeit aus eigenen Sensoren
- Rückwärtsgang zeigt automatisch ein camview-Layout, nach Ende mit Verzögerung ausgeblendet
- Diagnose: `LIVI erreichbar`, `camview erreichbar`
- Aktionen: `headunit.push_telemetry`, `headunit.camera_show`, `headunit.camera_hide`

## Installation

HACS → Benutzerdefiniertes Repository `https://github.com/trinler007/HA-Headunit` (Integration) → installieren → neu starten → Integration „Headunit (LIVI)“ hinzufügen.

Danach unter **Konfigurieren**: Fahrzeugdaten, GPS und Kameras zuordnen.

## Sicherheit

Die Telemetrie-API von LIVI (Port 4000) hat keine Authentifizierung. Wer sie erreicht, kann z. B. `reverse` setzen. Auf der Headunit den Port per Firewall nur für Home Assistant öffnen.

## Beispiele

```yaml
# Einzelwerte manuell
action: headunit.push_telemetry
data:
  data:
    notification:
      title: Frost
      text: Glatteisgefahr
      symbol: snowflake
      open: true

# Entsorgungskamera
action: headunit.camera_show
data:
  layout: entsorgen
```

## Lizenz

Apache License 2.0, siehe [LICENSE](LICENSE).
