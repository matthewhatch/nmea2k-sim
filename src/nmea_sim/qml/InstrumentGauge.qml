import QtQuick

Item {
    id: gauge
    property var reading: null
    property real minimum: 0
    property real maximum: 7000
    property int divisions: 7
    property string title: "ENGINE SPEED"
    property string unit: "RPM"
    property int decimals: 0
    property color accent: "#55e3cc"
    readonly property bool available: reading !== null && reading !== undefined
    property real displayed: available ? Math.max(minimum, Math.min(maximum, reading)) : minimum
    Behavior on displayed { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
    onDisplayedChanged: dial.requestPaint()
    onAvailableChanged: dial.requestPaint()
    onWidthChanged: dial.requestPaint()
    onHeightChanged: dial.requestPaint()
    Canvas {
        id: dial
        visible: gauge.height >= 240
        anchors.fill: parent
        onPaint: {
            var c = getContext("2d"); c.reset();
            var x = width/2, y = height*0.50, r = Math.min(width*0.43, height*0.42);
            var start = Math.PI*0.75, sweep = Math.PI*1.5;
            c.lineWidth = 12; c.lineCap = "round"; c.strokeStyle = "#243946";
            c.beginPath(); c.arc(x,y,r,start,start+sweep); c.stroke();
            if (gauge.available) {
                c.strokeStyle = gauge.accent;
                c.beginPath(); c.arc(x,y,r,start,start+sweep*(gauge.displayed-gauge.minimum)/(gauge.maximum-gauge.minimum)); c.stroke();
            }
            for (var i=0; i<=gauge.divisions*5; i++) {
                var a = start+sweep*i/(gauge.divisions*5);
                var major = i%5===0;
                c.lineWidth = major?2:1; c.strokeStyle = major?"#c9dce5":"#526f7e";
                c.beginPath(); c.moveTo(x+Math.cos(a)*(r-14),y+Math.sin(a)*(r-14));
                c.lineTo(x+Math.cos(a)*(r-(major?27:21)),y+Math.sin(a)*(r-(major?27:21))); c.stroke();
                if (major) {
                    c.font = "13px sans-serif"; c.textAlign = "center"; c.textBaseline = "middle";
                    c.fillStyle = "#a9c0cd";
                    var val = gauge.minimum+(gauge.maximum-gauge.minimum)*i/(gauge.divisions*5);
                    var label = gauge.maximum===7000 ? (val/1000).toFixed(0) : val.toFixed(0);
                    c.fillText(label,x+Math.cos(a)*(r-43),y+Math.sin(a)*(r-43));
                }
            }
            if (gauge.available) {
                var needle = start+sweep*(gauge.displayed-gauge.minimum)/(gauge.maximum-gauge.minimum);
                c.strokeStyle = "#edfaff"; c.lineWidth = 3;
                c.beginPath(); c.moveTo(x-Math.cos(needle)*12,y-Math.sin(needle)*12);
                c.lineTo(x+Math.cos(needle)*(r-52),y+Math.sin(needle)*(r-52)); c.stroke();
                c.beginPath(); c.arc(x,y,7,0,Math.PI*2); c.fillStyle=gauge.accent; c.fill();
            }
        }
    }
    Column {
        anchors.horizontalCenter: parent.horizontalCenter
        y: parent.height < 240 ? Math.max(0, (parent.height - height)/2 - 10) : parent.height*0.60
        spacing: 3
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: gauge.available ? Number(gauge.reading).toFixed(gauge.decimals) : "--"; color: "#f1fbff"; font.pixelSize: gauge.width>360?44:34; font.weight: Font.DemiBold }
        Text { anchors.horizontalCenter: parent.horizontalCenter; text: gauge.unit; color: gauge.accent; font.pixelSize: 12; font.letterSpacing: 2 }
    }
    Text { anchors.horizontalCenter: parent.horizontalCenter; y: Math.min(parent.height*0.91, parent.height - height); text: gauge.title; color: "#9cb8c7"; font.pixelSize: 11; font.letterSpacing: 2 }
}
