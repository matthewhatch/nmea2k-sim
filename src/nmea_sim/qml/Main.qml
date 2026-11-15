import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

ApplicationWindow {
    id: window
    width: 1280; height: 850
    minimumWidth: 940; minimumHeight: 700
    visible: true
    title: "NMEA · Engine Instruments"
    color: "#091820"
    font.family: "DejaVu Sans"
    palette.window: "#10232e"
    palette.base: "#142b38"
    palette.button: "#183743"
    palette.buttonText: "#c5e4ef"
    palette.text: "#e5f2fa"
    palette.highlight: "#55e3cc"
    palette.highlightedText: "#091820"
    palette.placeholderText: "#7897aa"
    property var data: dashboard.view
    property var counters: dashboard.stats
    property bool diagnosticsOpen: false
    readonly property color teal: "#55e3cc"
    readonly property string healthLabel: dashboard.connection === "error" ? "CAN INTERFACE ERROR" :
        dashboard.connection !== "connected" ? dashboard.connection.toUpperCase() :
        data.status === "fresh" ? "LIVE TELEMETRY" : data.status === "partial" ? "PARTIAL TELEMETRY" :
        data.status === "stale" ? "COMMUNICATION LOST" : "WAITING FOR ENGINE DATA"
    readonly property color healthColor: dashboard.connection === "error" || data.status === "stale" ? "#ff8c83" :
        data.status === "fresh" ? teal : "#e7be77"

    Rectangle { anchors { top: parent.top; left: parent.left; right: parent.right } height: 4; color: window.teal }
    ColumnLayout {
        anchors.fill: parent; anchors.margins: 28; spacing: 18
        RowLayout {
            Layout.fillWidth: true
            ColumnLayout {
                spacing: 4
                Text { text: "HELM  /  ENGINE"; color: "#ecf8ff"; font.pixelSize: 24; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                Text { text: "NMEA 2000 INSTRUMENTS    ·    RECEIVE ONLY"; color: "#6d91a6"; font.pixelSize: 10; font.letterSpacing: 1.2 }
            }
            Item { Layout.fillWidth: true }
            ComboBox {
                id: engineSelect; objectName: "engineSelector"
                Layout.preferredWidth: 252; model: dashboard.engines
                textRole: "label"; valueRole: "key"
                currentIndex: {
                    for (var i=0; i<count; i++) if (valueAt(i) === dashboard.selectedKey) return i;
                    return -1;
                }
                displayText: currentIndex < 0 ? "Select engine / source" : currentText
                onActivated: dashboard.selectEngine(currentValue)
            }
            Button { text: window.diagnosticsOpen ? "Instruments" : "Diagnostics"; onClicked: window.diagnosticsOpen = !window.diagnosticsOpen }
        }
        Rectangle {
            Layout.fillWidth: true; implicitHeight: 55
            color: "#112631"; border.color: "#263e4c"; radius: 10
            RowLayout {
                anchors { fill: parent; margins: 14 } spacing: 10
                Rectangle { width: 8; height: 8; radius: 4; color: window.healthColor }
                Text { objectName: "telemetryHealth"; text: window.healthLabel; color: window.healthColor; font.pixelSize: 11; font.weight: Font.DemiBold; font.letterSpacing: 1 }
                Item { Layout.fillWidth: true }
                Text { text: dashboard.channel + "   ·   " + Number(window.counters.rate || 0).toFixed(1) + " frames/s"; color: "#a1becd"; font.pixelSize: 12 }
                Text { text: window.data.running || "Unknown"; color: "#e5f2fa"; font.pixelSize: 12 }
            }
        }
        Text {
            Layout.fillWidth: true; visible: dashboard.connection !== "connected"
            text: dashboard.connectionDetail; wrapMode: Text.Wrap; color: "#ffb3a9"; font.pixelSize: 12
        }
        StackLayout {
            Layout.fillHeight: true; Layout.fillWidth: true
            currentIndex: window.diagnosticsOpen ? 1 : 0
            ColumnLayout {
                spacing: 16
                RowLayout {
                    Layout.fillHeight: true; Layout.fillWidth: true; spacing: 16
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 600
                        color: "#10232e"; border.color: "#243d4b"; radius: 16
                        InstrumentGauge { id: rpmGauge; objectName: "rpmGauge"; anchors.fill: parent; anchors.margins: 8; reading: window.data.rpm; title: "ENGINE SPEED · ×1000"; unit: "RPM" }
                    }
                    Rectangle {
                        Layout.fillWidth: true; Layout.fillHeight: true; Layout.preferredWidth: 420
                        color: "#10232e"; border.color: "#243d4b"; radius: 16
                        InstrumentGauge { objectName: "temperatureGauge"; anchors.fill: parent; anchors.margins: 8; reading: window.data.temperature_c; minimum: 0; maximum: 120; divisions: 6; title: "ENGINE TEMPERATURE"; unit: "°C"; decimals: 1; accent: "#78bbef" }
                    }
                }
                GridLayout {
                    Layout.fillWidth: true; columns: 4; columnSpacing: 12; rowSpacing: 12
                    MetricTile { Layout.fillWidth: true; title: "ALTERNATOR"; units: "V"; reading: window.data.voltage_v }
                    MetricTile { Layout.fillWidth: true; title: "OIL PRESSURE"; units: "bar"; reading: window.data.oil_pressure_bar; decimals: 2 }
                    MetricTile { Layout.fillWidth: true; title: "FUEL RATE"; units: "L/h"; reading: window.data.fuel_rate_lph }
                    MetricTile { Layout.fillWidth: true; title: "ENGINE HOURS"; units: "h"; reading: window.data.engine_hours; decimals: 2 }
                    MetricTile { Layout.fillWidth: true; title: "TRIM"; units: "%"; reading: window.data.trim; decimals: 0 }
                    MetricTile { objectName: "oilTemperatureTile"; Layout.fillWidth: true; title: "OIL TEMPERATURE"; units: "°C"; reading: window.data.oil_temperature_c }
                    MetricTile { objectName: "fuelPressureTile"; Layout.fillWidth: true; title: "FUEL PRESSURE"; units: "bar"; reading: window.data.fuel_pressure_bar; decimals: 2 }
                    MetricTile { objectName: "engineLoadTile"; Layout.fillWidth: true; title: "ENGINE LOAD"; units: "%"; reading: window.data.engine_load_pct; decimals: 0 }
                }
                Rectangle {
                    Layout.fillWidth: true; implicitHeight: 72; color: "#10232e"; border.color: "#243d4b"; radius: 12
                    ColumnLayout {
                        anchors { fill: parent; margins: 13 } spacing: 9
                        Text { text: "NMEA-REPORTED ENGINE STATUS"; color: "#708fa2"; font.pixelSize: 9; font.letterSpacing: 1 }
                        RowLayout {
                            Layout.fillWidth: true
                            Repeater {
                                model: [{label:"High temperature", flag:window.data.high_temperature},
                                        {label:"Low oil pressure", flag:window.data.low_oil_pressure},
                                        {label:"Low voltage", flag:window.data.low_voltage},
                                        {label:"Engine warnings", flag:window.data.warning_known ? window.data.warnings.length > 0 : null}]
                                Row {
                                    required property var modelData
                                    Layout.fillWidth: true; spacing: 8
                                    Rectangle { width: 7; height: 7; radius: 4; anchors.verticalCenter: parent.verticalCenter; color: modelData.flag === null || modelData.flag === undefined ? "#526775" : modelData.flag ? "#ff8c83" : "#55e3cc" }
                                    Text { text: modelData.label + (modelData.flag === null || modelData.flag === undefined ? "  --" : modelData.flag ? "  ACTIVE" : "  Clear"); color: modelData.flag ? "#ffb3a9" : "#a4bfcc"; font.pixelSize: 10 }
                                }
                            }
                        }
                    }
                }
                Text { Layout.fillWidth: true; text: window.data.warning_known && window.data.warnings.length ? window.data.warnings.join(" · ") : "Unavailable or stale measurements show --. Grey status indicators mean unknown."; color: window.data.warnings && window.data.warnings.length ? "#ffb3a9" : "#6f90a4"; font.pixelSize: 10; wrapMode: Text.Wrap }
            }
            ColumnLayout {
                spacing: 12
                RowLayout {
                    Layout.fillWidth: true
                    TextField { id: pgnFilter; placeholderText: "PGN (all)"; Layout.preferredWidth: 165 }
                    TextField { id: sourceFilter; placeholderText: "Source (all)"; Layout.preferredWidth: 150 }
                    Button { text: "Apply filters"; onClicked: filterError.visible = !dashboard.filterDiagnostics(pgnFilter.text, sourceFilter.text) }
                    Button { text: "Clear"; onClicked: { pgnFilter.text=""; sourceFilter.text=""; filterError.visible=false; dashboard.filterDiagnostics("", ""); } }
                    Button { text: dashboard.diagnosticsPaused ? "Resume view" : "Pause view"; onClicked: dashboard.toggleDiagnosticsPause() }
                    Item { Layout.fillWidth: true }
                }
                Text { Layout.fillWidth: true; text: window.counters.transport + " / " + dashboard.channel + (window.counters.transport === "socketcand" ? " @ " + window.counters.host + ":" + window.counters.port : "") + " · " + dashboard.connection + " · Retries " + window.counters.reconnections + " · Transport errors " + window.counters.transport_errors + " · Parse errors " + window.counters.parsing_errors + " · Last frame " + (window.counters.last_timestamp || "none") + "\nFrames " + window.counters.received + "   Messages " + window.counters.decoded_count + "   Malformed " + window.counters.malformed + "   Reassembly " + window.counters.fast_error_count; color: "#acc6d4"; font.pixelSize: 11; wrapMode: Text.Wrap }
                Text { id: filterError; visible: false; text: "Enter decimal PGN 0–262143 and source 0–255."; color: "#ffb3a9"; font.pixelSize: 12 }
                Text { Layout.fillWidth: true; text: "Fast-packet errors: " + JSON.stringify(window.counters.fast_errors || {}) + "   ·   UI frames dropped: " + window.counters.dropped; color: "#7298af"; font.pixelSize: 10; wrapMode: Text.Wrap }
                Rectangle {
                    Layout.fillWidth: true; Layout.fillHeight: true; color: "#0d202b"; radius: 12; border.color: "#243d4b"
                    ListView {
                        id: trace; objectName: "diagnosticList"; anchors.fill: parent; anchors.margins: 12
                        clip: true; spacing: 8; model: dashboard.diagnostics
                        ScrollBar.vertical: ScrollBar {}
                        delegate: Rectangle {
                            required property var modelData
                            width: trace.width; height: traceContent.implicitHeight + 18
                            color: modelData.error ? "#38272c" : "#142b38"; radius: 6
                            Column {
                                id: traceContent; anchors { left: parent.left; right: parent.right; top: parent.top; margins: 9 } spacing: 5
                                Text { text: modelData.timestamp_text + "   ID " + modelData.id + "   PGN " + modelData.pgn + "   SRC " + modelData.source + "   " + modelData.kind; color: "#b6d6e5"; font.family: "DejaVu Sans Mono"; font.pixelSize: 10 }
                                Text { text: modelData.payload; color: "#55e3cc"; font.family: "DejaVu Sans Mono"; font.pixelSize: 11 }
                                Text { width: parent.width; text: modelData.error || modelData.decoded_text || "No completed decoded message for this frame"; color: "#789db2"; font.pixelSize: 10; wrapMode: Text.WrapAnywhere }
                            }
                        }
                    }
                }
            }
        }
        RowLayout {
            Layout.fillWidth: true
            Text { text: "ENGINE " + (window.data.instance === null || window.data.instance === undefined ? "--" : window.data.instance) + "   /   SOURCE " + (window.data.source === null || window.data.source === undefined ? "--" : window.data.source); color: "#8dabbc"; font.pixelSize: 10; font.letterSpacing: 1 }
            Item { Layout.fillWidth: true }
            Text { text: "Rapid " + (window.data.rapid_fresh ? "live" : "unavailable / stale") + "   ·   Dynamic " + (window.data.dynamic_fresh ? "live" : "unavailable / stale"); color: "#6f90a4"; font.pixelSize: 10 }
            Button { text: "Reconnect"; onClicked: dashboard.start() }
        }
    }
}
