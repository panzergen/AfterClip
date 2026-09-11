import QtQuick
import QtQuick.Controls.Basic

Column {
    id: root

    signal stepUp()
    signal stepDown()

    spacing: 1

    Rectangle {
        width: 20
        height: 14
        color: upMouse.containsMouse ? "#f2f3f5" : "#e9e9e9"
        border.color: "#adadad"
        radius: 2

        Text {
            anchors.centerIn: parent
            text: "\u25B2"
            font.pixelSize: 8
            color: Theme.text
        }

        MouseArea {
            id: upMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.stepUp()
        }

        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Increase clip time")
    }

    Rectangle {
        width: 20
        height: 14
        color: downMouse.containsMouse ? "#f2f3f5" : "#e9e9e9"
        border.color: "#adadad"
        radius: 2

        Text {
            anchors.centerIn: parent
            text: "\u25BC"
            font.pixelSize: 8
            color: Theme.text
        }

        MouseArea {
            id: downMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.stepDown()
        }

        Accessible.role: Accessible.Button
        Accessible.name: qsTr("Decrease clip time")
    }
}
