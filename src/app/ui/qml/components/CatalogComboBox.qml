import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

// Model picker with per-provider accordion sections. The catalog is a flat list
// whose provider headers are collapsible; selecting a model calls back into the
// job form with the entry index so provider/model resolution stays in Python.
Button {
    id: root

    property bool vision: false
    // provider id -> true when its section is collapsed
    property var collapsed: ({})

    readonly property var entries: root.vision ? jobForm.visionEntries : jobForm.analysisEntries
    readonly property string currentModel: root.vision
                                             ? jobForm.visionModelText
                                             : jobForm.analysisModelText

    text: root.currentModel.length > 0 ? root.currentModel : qsTr("Select a model")
    enabled: root.vision ? jobForm.visionModelEnabled : jobForm.analysisModelEnabled
    font.pixelSize: Theme.fontSizeSmall
    implicitHeight: Theme.controlHeight

    contentItem: Text {
        text: root.text
        font: root.font
        elide: Text.ElideRight
        verticalAlignment: Text.AlignVCenter
        leftPadding: 8
        rightPadding: 8
        color: root.enabled ? Theme.text : Theme.muted
    }

    background: Rectangle {
        color: Theme.field
        border.color: root.activeFocus || popup.opened ? Theme.primary : Theme.fieldBorder
        radius: 3
    }

    onClicked: popup.opened ? popup.close() : popup.open()

    Popup {
        id: popup
        y: root.height
        width: root.width
        padding: 1
        implicitHeight: Math.min(list.contentHeight + 2, 360)

        contentItem: ListView {
            id: list
            clip: true
            model: root.entries
            implicitHeight: contentHeight
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator {}

            delegate: ItemDelegate {
                id: entry
                required property int index
                required property var modelData
                width: list.width
                font.pixelSize: Theme.fontSizeSmall

                readonly property bool isHeader: modelData.header === true
                readonly property bool collapsedSection: !isHeader
                    && root.collapsed[modelData.provider] === true
                visible: !collapsedSection
                height: collapsedSection ? 0 : implicitHeight

                contentItem: Text {
                    text: (entry.isHeader
                           ? (root.collapsed[entry.modelData.provider] === true ? "\u25B6  " : "\u25BC  ")
                           : "     ") + (entry.modelData.label || "")
                    font.pixelSize: Theme.fontSizeSmall
                    font.bold: entry.isHeader
                    elide: Text.ElideRight
                    verticalAlignment: Text.AlignVCenter
                    color: entry.isHeader ? Theme.muted : Theme.text
                }

                background: Rectangle {
                    color: entry.isHeader
                           ? "#eef1f5"
                           : (entry.hovered ? "#e6eef8" : "transparent")
                }

                onClicked: {
                    if (entry.isHeader) {
                        const next = Object.assign({}, root.collapsed)
                        next[entry.modelData.provider] = !(next[entry.modelData.provider] === true)
                        root.collapsed = next
                    } else {
                        if (root.vision)
                            jobForm.selectVisionModel(entry.index)
                        else
                            jobForm.selectAnalysisModel(entry.index)
                        popup.close()
                    }
                }
            }
        }

        background: Rectangle {
            color: Theme.field
            border.color: Theme.border
            radius: 3
        }
    }
}
