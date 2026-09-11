import QtQuick
import QtQuick.Controls.Basic

FieldRow {
    id: root

    property bool vision: false

    label: root.vision ? qsTr("Vision model") : qsTr("Model")

    ComboBox {
        id: combo
        width: parent.width
        editable: true
        enabled: root.vision ? jobForm.visionModelEnabled : jobForm.analysisModelEnabled
        model: root.vision ? jobForm.visionEntries : jobForm.analysisEntries
        // Show the current model immediately; the Connections below keep it in
        // sync after the user has typed and broken this binding.
        editText: root.vision ? jobForm.visionModelText : jobForm.analysisModelText
        font.pixelSize: Theme.fontSizeSmall

        property bool syncing: false

        function syncEditText(text) {
            syncing = true
            editText = text
            syncing = false
        }

        delegate: ItemDelegate {
            id: entryDelegate
            required property int index
            required property var modelData
            width: combo.width
            enabled: !modelData.header
            highlighted: combo.highlightedIndex === index
            font.pixelSize: Theme.fontSizeSmall

            // Explicit colours: the highlighted row otherwise inherits a
            // combination where the active model becomes unreadable.
            contentItem: Text {
                text: entryDelegate.modelData.label
                font: entryDelegate.font
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideRight
                color: entryDelegate.highlighted
                       ? "#ffffff"
                       : (entryDelegate.enabled ? Theme.text : Theme.muted)
            }

            background: Rectangle {
                color: entryDelegate.highlighted
                       ? Theme.primary
                       : (entryDelegate.enabled ? "transparent" : Theme.panel)
            }
        }

        onActivated: (index) => {
            if (root.vision)
                jobForm.selectVisionModel(index)
            else
                jobForm.selectAnalysisModel(index)
        }
        onAccepted: {
            if (root.vision)
                jobForm.visionModelText = editText
            else
                jobForm.analysisModelText = editText
        }

        Connections {
            target: jobForm
            function onAnalysisModelTextChanged() {
                if (!root.vision && !combo.activeFocus)
                    combo.syncEditText(jobForm.analysisModelText)
            }
            function onVisionModelTextChanged() {
                if (root.vision && !combo.activeFocus)
                    combo.syncEditText(jobForm.visionModelText)
            }
        }
    }
}
