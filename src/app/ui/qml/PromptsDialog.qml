import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

Dialog {
    id: root

    title: qsTr("Prompt templates")
    modal: true
    standardButtons: Dialog.Close
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: 620
    height: Math.min(660, Overlay.overlay ? Overlay.overlay.height - 56 : 660)
    onOpened: presets.refresh()

    contentItem: ColumnLayout {
        spacing: 8

        RowLayout {
            spacing: 8
            Text {
                text: qsTr("Preset")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
            AppComboBox {
                id: presetCombo
                Layout.fillWidth: true
                model: presets.names
                currentIndex: presets.selectedIndex
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => { presets.selectedIndex = index; presets.loadSelectedPrompts() }
            }
            Button {
                text: qsTr("Apply")
                font.pixelSize: Theme.fontSizeSmall
                enabled: presets.hasPresets
                onClicked: presets.applySelected()
            }
        }

        RowLayout {
            spacing: 8
            Text {
                Layout.fillWidth: true
                text: presets.hasPresets && presets.selectedName.length > 0 ? qsTr("Editing '%1' — Prompts: %2").arg(presets.selectedName).arg(presets.promptBadge) : qsTr("No presets yet")
                font.pixelSize: Theme.fontSizeCaption
                color: Theme.muted
                wrapMode: Text.Wrap
            }
            Button {
                text: qsTr("Use preset prompts")
                font.pixelSize: Theme.fontSizeSmall
                visible: presets.hasPresets && presets.promptBadge === "Custom"
                onClicked: presets.usePresetPrompts()
            }
        }

        RowLayout {
            spacing: 8
            TextField {
                Layout.fillWidth: true
                placeholderText: qsTr("New preset name")
                text: presets.newName
                font.pixelSize: Theme.fontSizeSmall
                selectByMouse: true
                onTextEdited: presets.newName = text
            }
            Button {
                text: qsTr("Create preset")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: presets.saveCurrent()
            }
        }

        RowLayout {
            spacing: 8
            Text {
                text: qsTr("Template")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
            AppComboBox {
                id: nameCombo
                Layout.fillWidth: true
                model: settings.promptNames
                currentIndex: settings.promptIndex
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => settings.selectPrompt(index)
            }
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("Placeholders: ") + settings.promptPlaceholders.join(", ")
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }

        ScrollView {
            Layout.fillWidth: true
            Layout.fillHeight: true
            TextArea {
                id: promptArea
                text: settings.promptText
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                font.pixelSize: Theme.fontSizeSmall
                // onTextEdited fires only for user input, so the binding above
                // stays intact when the selected template changes.
                onTextEdited: settings.promptText = text
                background: Rectangle {
                    color: Theme.field
                    border.color: promptArea.activeFocus ? Theme.primary : Theme.fieldBorder
                    radius: 3
                }
            }
        }

        Text {
            Layout.fillWidth: true
            text: settings.promptStatusText
            font.pixelSize: Theme.fontSizeCaption
            color: settings.promptStatusOk ? Theme.ok : Theme.danger
            wrapMode: Text.Wrap
        }

        Text {
            Layout.fillWidth: true
            visible: settings.promptDirty
            text: qsTr("Unsaved changes — used for the next job")
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }

        Row {
            spacing: 8
            Button {
                text: qsTr("Save")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: settings.savePrompt()
                ToolTip.visible: hovered
                ToolTip.delay: 400
                ToolTip.text: qsTr("Save this template to the global prompts only. The selected preset is unchanged.")
            }
            Button {
                text: presets.selectedName.length > 0 ? qsTr("Save to '%1'").arg(presets.selectedName) : qsTr("Save to preset")
                font.pixelSize: Theme.fontSizeSmall
                enabled: presets.hasPresets
                onClicked: presets.updateSelectedPrompts()
                ToolTip.visible: hovered
                ToolTip.delay: 400
                ToolTip.text: qsTr("Save all templates into the selected preset (full snapshot) and activate them globally.")
            }
            Button {
                text: qsTr("Reset to default")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: settings.resetPrompt()
            }
            Button {
                text: qsTr("Reload")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: settings.reloadPrompts()
            }
        }

        Text {
            Layout.fillWidth: true
            visible: presets.statusText.length > 0
            text: presets.statusText
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }
    }
}
