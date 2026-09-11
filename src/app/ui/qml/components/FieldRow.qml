import QtQuick
import QtQuick.Layouts

RowLayout {
    id: root

    default property alias content: host.data
    property string label: ""
    property real labelWidth: 120

    spacing: 8

    Text {
        Layout.preferredWidth: root.labelWidth
        Layout.alignment: Qt.AlignVCenter
        text: root.label
        font.pixelSize: Theme.fontSizeSmall
        color: Theme.muted
    }

    Item {
        id: host
        Layout.fillWidth: true
        Layout.alignment: Qt.AlignVCenter
        implicitHeight: childrenRect.height
    }
}
