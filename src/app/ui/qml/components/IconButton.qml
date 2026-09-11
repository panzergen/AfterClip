import QtQuick
import QtQuick.Controls.Basic

AbstractButton {
    id: root

    property string glyph: ""
    property string toolTip: ""
    property bool showCheckState: false

    implicitWidth: Theme.iconButtonSize
    implicitHeight: Theme.iconButtonSize
    checkable: showCheckState
    Accessible.name: root.toolTip || root.glyph

    background: Rectangle {
        color: root.pressed ? "#d7dade" : (root.hovered ? "#f2f3f5" : "#e9e9e9")
        border.color: root.checked ? Theme.primary : "#adadad"
        border.width: root.checked ? 2 : 1
        radius: 3
    }

    contentItem: Text {
        text: root.glyph
        font.pixelSize: Theme.fontSizeBody
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
    }

    ToolTip.visible: hovered && toolTip.length > 0
    ToolTip.delay: 400
    ToolTip.text: toolTip
}
