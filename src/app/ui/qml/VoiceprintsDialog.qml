import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import "components"

Dialog {
    id: root

    title: qsTr("Voiceprints")
    modal: true
    standardButtons: Dialog.Close
    parent: Overlay.overlay
    anchors.centerIn: Overlay.overlay
    width: 600
    height: Math.min(560, Overlay.overlay ? Overlay.overlay.height - 56 : 560)

    property int pendingReenrollIndex: -1

    contentItem: ScrollView {
        id: scroll
        contentWidth: availableWidth
        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

        ColumnLayout {
            width: scroll.availableWidth
            spacing: 8

            Text {
                Layout.fillWidth: true
                text: settings.voiceprintAvailable
                    ? qsTr("Matches enrolled speakers and clusters unknowns into Speaker N. Complements (never overrides) the speaker VTT. Embeddings are stored locally.")
                    : qsTr("Voiceprint support is not installed. Install the optional 'voiceprint' extra (onnxruntime + speakeronnx) to enable it.")
                font.pixelSize: Theme.fontSizeCaption
                color: settings.voiceprintAvailable ? Theme.muted : Theme.danger
                wrapMode: Text.Wrap
            }

            RowLayout {
                spacing: 8
                Text {
                    Layout.preferredWidth: 150
                    text: qsTr("Identify threshold")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }
                SpinBox {
                    from: 0
                    to: 100
                    stepSize: 5
                    value: Math.round(settings.voiceprintIdentifyThreshold * 100)
                    editable: true
                    onValueModified: settings.voiceprintIdentifyThreshold = value / 100.0
                }
            }

            RowLayout {
                spacing: 8
                Text {
                    Layout.preferredWidth: 150
                    text: qsTr("Cluster threshold")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }
                SpinBox {
                    from: 0
                    to: 100
                    stepSize: 5
                    value: Math.round(settings.voiceprintClusterThreshold * 100)
                    editable: true
                    onValueModified: settings.voiceprintClusterThreshold = value / 100.0
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Saved speakers")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }

            Column {
                Layout.fillWidth: true
                spacing: 4

                Repeater {
                    model: settings.voiceprintNames
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        Text {
                            Layout.fillWidth: true
                            text: modelData
                            font.pixelSize: Theme.fontSizeSmall
                        }
                        Button {
                            text: qsTr("Re-enroll")
                            font.pixelSize: Theme.fontSizeSmall
                            enabled: settings.voiceprintAvailable
                            onClicked: {
                                root.pendingReenrollIndex = index
                                reenrollDialog.open()
                            }
                        }
                        Button {
                            text: qsTr("Reset")
                            font.pixelSize: Theme.fontSizeSmall
                            onClicked: settings.removeVoiceprint(index)
                        }
                    }
                }

                Text {
                    visible: settings.voiceprintNames.length === 0
                    text: qsTr("No saved voiceprints yet. Enroll a speaker below.")
                    font.pixelSize: Theme.fontSizeCaption
                    color: Theme.faint
                }
            }

            Text {
                Layout.fillWidth: true
                text: qsTr("Enroll a speaker from a short clean audio sample")
                font.pixelSize: Theme.fontSizeSmall
                color: Theme.muted
            }

            RowLayout {
                spacing: 8
                Text {
                    Layout.preferredWidth: 100
                    text: qsTr("Name")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }
                TextField {
                    Layout.fillWidth: true
                    placeholderText: qsTr("e.g. Alice")
                    text: settings.voiceprintEnrollName
                    font.pixelSize: Theme.fontSizeSmall
                    selectByMouse: true
                    onTextEdited: settings.voiceprintEnrollName = text
                }
            }

            RowLayout {
                spacing: 8
                Text {
                    Layout.preferredWidth: 100
                    text: qsTr("Sample audio")
                    font.pixelSize: Theme.fontSizeSmall
                    color: Theme.muted
                }
                TextField {
                    Layout.fillWidth: true
                    placeholderText: qsTr("Path to a short WAV/audio sample")
                    text: settings.voiceprintEnrollPath
                    font.pixelSize: Theme.fontSizeSmall
                    selectByMouse: true
                    onTextEdited: settings.voiceprintEnrollPath = text
                }
                Button {
                    text: qsTr("Enroll")
                    font.pixelSize: Theme.fontSizeSmall
                    enabled: settings.voiceprintAvailable
                    onClicked: settings.enrollVoiceprint()
                }
            }

            Text {
                visible: settings.voiceprintStatusText.length > 0
                text: settings.voiceprintStatusText
                font.pixelSize: Theme.fontSizeCaption
                color: Theme.muted
                wrapMode: Text.Wrap
                Layout.fillWidth: true
            }
        }
    }

    FileDialog {
        id: reenrollDialog
        title: qsTr("Choose a new sample for this speaker")
        fileMode: FileDialog.OpenFile
        nameFilters: [qsTr("Audio (*.wav *.mp3 *.m4a *.flac *.ogg)")]
        onAccepted: {
            settings.reenrollVoiceprint(root.pendingReenrollIndex, selectedFile)
            root.pendingReenrollIndex = -1
        }
    }
}
