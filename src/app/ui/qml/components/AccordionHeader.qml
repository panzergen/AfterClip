import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root

    property string title: ""
    property bool expanded: true

    signal toggled()

    implicitHeight: 30
    color: Theme.panel
    border.color: Theme.border
    radius: 4

    Text {
        anchors.left: parent.left
        anchors.leftMargin: 10
        anchors.verticalCenter: parent.verticalCenter
        text: (root.expanded ? "\u25BC " : "\u25B6 ") + root.title
        font.pixelSize: Theme.fontSizeSmall
        font.weight: Font.DemiBold
        color: Theme.text
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: root.toggled()
    }

    Accessible.role: Accessible.Button
    Accessible.name: root.title
}
