import QtQuick
import QtQuick.Controls.Basic

// Shared combo box styling: the default Basic delegate can render the active
// (highlighted) or hovered row with the same foreground and background colour,
// making the selection unreadable. This delegate pins explicit colours.
ComboBox {
    id: root
    font.pixelSize: Theme.fontSizeSmall

    delegate: ItemDelegate {
        id: entry
        required property int index
        required property var modelData
        width: root.width
        highlighted: root.highlightedIndex === index
        font.pixelSize: Theme.fontSizeSmall

        readonly property string labelText: {
            const data = entry.modelData
            if (data !== null && data !== undefined && typeof data === "object") {
                if (root.textRole && data[root.textRole] !== undefined)
                    return String(data[root.textRole])
                if (data.label !== undefined)
                    return String(data.label)
                if (data.name !== undefined)
                    return String(data.name)
                return ""
            }
            return String(data)
        }

        contentItem: Text {
            text: entry.labelText
            font: entry.font
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
            color: entry.highlighted ? "#ffffff" : (entry.enabled ? Theme.text : Theme.muted)
        }

        background: Rectangle {
            color: entry.highlighted
                   ? Theme.primary
                   : (entry.hovered ? "#e6eef8" : "transparent")
        }
    }
}
