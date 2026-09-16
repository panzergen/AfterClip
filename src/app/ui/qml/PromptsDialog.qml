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
    height: Math.min(560, Overlay.overlay ? Overlay.overlay.height - 56 : 560)

    contentItem: ColumnLayout {
        spacing: 8

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

        Row {
            spacing: 8
            Button {
                text: qsTr("Save")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: settings.savePrompt()
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
    }
}
