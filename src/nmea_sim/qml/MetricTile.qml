import QtQuick
import QtQuick.Layouts

Rectangle {
    id: tile
    property string title: ""
    property string units: ""
    property var reading: null
    property int decimals: 1
    color: "#122633"; border.color: "#243d4b"; radius: 12
    implicitHeight: 108
    Column {
        anchors { left: parent.left; right: parent.right; top: parent.top; margins: 18 }
        spacing: 9
        Text { text: tile.title; color: "#91acbc"; font.pixelSize: 11; font.letterSpacing: 1.5 }
        Row {
            spacing: 9
            Text { text: tile.reading === null || tile.reading === undefined ? "--" : Number(tile.reading).toFixed(tile.decimals); color: "#ecf8ff"; font.pixelSize: 30; font.weight: Font.DemiBold }
            Text { text: tile.units; color: "#7897aa"; font.pixelSize: 13; anchors.baseline: parent.children[0].baseline }
        }
    }
}
