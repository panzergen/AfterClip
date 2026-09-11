import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root

    property bool cloudSelected: false
    signal cloudToggled()
    signal localToggled()

    implicitHeight: 36

    Rectangle {
        id: frame
        anchors.fill: parent
        color: "transparent"
        border.color: Theme.primary
        radius: 4
    }

    Row {
        anchors.fill: parent

        Rectangle {
            width: parent.width / 2
            height: parent.height
            color: root.cloudSelected ? Theme.primary : "transparent"
            radius: 4

            Text {
                anchors.centerIn: parent
                text: qsTr("\u2601 Cloud (Gemini)")
                font.pixelSize: Theme.fontSizeSmall
                font.weight: root.cloudSelected ? Font.DemiBold : Font.Normal
                color: root.cloudSelected ? "#ffffff" : Theme.primary
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.cloudToggled()
            }
        }

        Rectangle {
            width: parent.width / 2
            height: parent.height
            color: !root.cloudSelected ? Theme.primary : "transparent"
            radius: 4

            Text {
                anchors.centerIn: parent
                text: qsTr("\uD83D\uDD12 Local (Ollama)")
                font.pixelSize: Theme.fontSizeSmall
                font.weight: !root.cloudSelected ? Font.DemiBold : Font.Normal
                color: !root.cloudSelected ? "#ffffff" : Theme.primary
            }

            MouseArea {
                anchors.fill: parent
                cursorShape: Qt.PointingHandCursor
                onClicked: root.localToggled()
            }
        }
    }
}
