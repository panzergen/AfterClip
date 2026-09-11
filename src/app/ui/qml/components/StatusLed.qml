import QtQuick
import QtQuick.Controls.Basic

Item {
    id: root
    width: 16
    height: 16

    property bool ok: false
    property string checksText: ""

    Rectangle {
        anchors.fill: parent
        radius: 8
        color: root.ok ? Theme.ledGreen : Theme.ledRed
    }

    Popup {
        id: popup
        y: -height - 6
        x: -width + parent.width
        padding: 8
        background: Rectangle {
            color: Theme.popupBg
            border.color: "#4a4f57"
            radius: 4
        }
        contentItem: Text {
            text: root.checksText
            color: Theme.popupFg
            font.pixelSize: Theme.fontSizeSmall
        }
    }

    HoverHandler {
        onHoveredChanged: popup.visible = hovered && root.checksText.length > 0
    }

    Accessible.role: Accessible.Indicator
    Accessible.name: root.checksText
}
