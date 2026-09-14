import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

Dialog {
    id: root

    title: qsTr("AfterClip Settings")
    modal: true
    standardButtons: Dialog.Ok | Dialog.Cancel
    // The dialog is instantiated by a Loader (zero-sized parent), so center on
    // the window overlay instead and cap against the window height.
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: 540
    // Grow with the content but never overflow the window; the ScrollView
    // below keeps the footer buttons reachable on short screens.
    height: Math.min(
        contentColumn.implicitHeight + 110,
        Overlay.overlay ? Math.max(360, Overlay.overlay.height - 48) : 640
    )

    onAccepted: {
        settings.save()
        session.onSettingsSaved()
    }

    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            id: contentColumn
            width: scroll.availableWidth
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

            RowLayout {
                Layout.fillWidth: true
                Button {
                    text: qsTr("Edit prompt templates…")
                    font.pixelSize: Theme.fontSizeSmall
                    onClicked: promptsDialog.open()
                }
                Item { Layout.fillWidth: true }
            }

            GroupBox {
                id: geminiGroup
                Layout.fillWidth: true
                // GroupBox does not derive its implicit height from an
                // anchors.fill child, so bind it explicitly or the dialog
                // under-sizes and the footer overlaps the content.
                implicitHeight: geminiLayout.implicitHeight + topPadding + bottomPadding
                title: qsTr("Gemini (cloud provider)")
                font.pixelSize: Theme.fontSizeSmall

                background: Rectangle {
                    color: Theme.panel
                    border.color: Theme.border
                    radius: 4
                }

                ColumnLayout {
                    id: geminiLayout
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
        }
    }

    PromptsDialog {
        id: promptsDialog
    }
}
