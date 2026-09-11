import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

Dialog {
    id: root

    title: qsTr("AfterClip Settings")
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel
    width: 520
    anchors.centerIn: parent

    onAccepted: {
        settings.save()
        session.onSettingsSaved()
    }

    contentItem: ColumnLayout {
        spacing: 8

        RowLayout {
            spacing: 8
            Text {
                Layout.preferredWidth: 170
                text: qsTr("Transcript segment length")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
            ComboBox {
                Layout.preferredWidth: 240
                model: settings.segmentLabels
                currentIndex: settings.segmentIndex
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => settings.segmentIndex = index
            }
        }

        Text {
            Layout.fillWidth: true
            text: qsTr("Whisper default keeps raw segments; 15/30/60 merge into paragraph blocks (30s = standard). Per-job override lives in the Advanced panel.")
            font.pixelSize: Theme.fontSizeCaption
            color: Theme.muted
            wrapMode: Text.Wrap
        }

        RowLayout {
            spacing: 8
            Text {
                Layout.preferredWidth: 170
                text: qsTr("Report language")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }
            TextField {
                Layout.fillWidth: true
                placeholderText: qsTr("Optional, e.g. tr — default report language for new jobs")
                text: settings.reportLanguage
                font.pixelSize: Theme.fontSizeSmall
                selectByMouse: true
                onEditingFinished: settings.reportLanguage = text
                background: Rectangle {
                    color: Theme.field
                    border.color: parent.activeFocus ? Theme.primary : Theme.fieldBorder
                    radius: 3
                }
            }
        }

        GroupBox {
            Layout.fillWidth: true
            title: qsTr("Gemini (cloud provider)")
            font.pixelSize: Theme.fontSizeSmall

            background: Rectangle {
                color: Theme.panel
                border.color: Theme.border
                radius: 4
            }

            ColumnLayout {
                anchors.fill: parent
                spacing: 8

                RowLayout {
                    spacing: 8
                    Text {
                        Layout.preferredWidth: 90
                        text: qsTr("Model")
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.muted
                    }
                    ComboBox {
                        id: geminiModelCombo
                        Layout.fillWidth: true
                        editable: true
                        model: settings.modelOptions
                        editText: settings.geminiModel
                        font.pixelSize: Theme.fontSizeSmall
                        onAccepted: settings.geminiModel = editText
                    }
                    Button {
                        text: qsTr("Load models")
                        font.pixelSize: Theme.fontSizeSmall
                        ToolTip.visible: hovered
                        ToolTip.delay: 400
                        ToolTip.text: qsTr("Fetches the current model list from the Gemini API using the stored key")
                        onClicked: settings.loadModels()
                    }
                }

                RowLayout {
                    spacing: 8
                    Text {
                        Layout.preferredWidth: 90
                        text: qsTr("API key")
                        font.pixelSize: Theme.fontSizeSmall
                        color: Theme.muted
                    }
                    TextField {
                        id: keyField
                        Layout.fillWidth: true
                        echoMode: TextInput.Password
                        placeholderText: qsTr("Paste API key (stored in the OS credential manager)")
                        font.pixelSize: Theme.fontSizeSmall
                        selectByMouse: true
                        onTextEdited: settings.keyInput = text
                        background: Rectangle {
                            color: Theme.field
                            border.color: keyField.activeFocus ? Theme.primary : Theme.fieldBorder
                            radius: 3
                        }
                    }
                }

                Row {
                    spacing: 8
                    Button {
                        text: qsTr("Save key")
                        font.pixelSize: Theme.fontSizeSmall
                        onClicked: {
                            settings.saveKey()
                            keyField.text = ""
                        }
                    }
                    Button {
                        text: qsTr("Delete key")
                        font.pixelSize: Theme.fontSizeSmall
                        onClicked: settings.deleteKey()
                    }
                }

                Text {
                    text: settings.keyStatusText
                    font.pixelSize: Theme.fontSizeCaption
                    color: settings.keyStored ? Theme.ok : Theme.danger
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Text {
                    text: settings.cloudConsentText
                    font.pixelSize: Theme.fontSizeCaption
                    color: settings.cloudConsentGranted ? Theme.ok : Theme.muted
                    wrapMode: Text.Wrap
                    Layout.fillWidth: true
                }

                Row {
                    spacing: 8
                    Button {
                        text: qsTr("Grant consent")
                        font.pixelSize: Theme.fontSizeSmall
                        enabled: !settings.cloudConsentGranted
                        onClicked: settings.grantGeminiConsent()
                    }
                    Button {
                        text: qsTr("Revoke consent")
                        font.pixelSize: Theme.fontSizeSmall
                        enabled: settings.cloudConsentGranted
                        onClicked: settings.revokeGeminiConsent()
                    }
                }
            }
        }

        Item { Layout.fillHeight: true }
    }
}
