import QtQuick
import QtQuick.Layouts
import QtQuick.Controls.Basic
import "components"

ColumnLayout {
    id: root

    property bool transcriptExpanded: true
    property bool aiExpanded: true
    property bool visualExpanded: true

    Layout.fillWidth: true
    spacing: 6

    // -- Presets -------------------------------------------------------------
    FieldRow {
        Layout.fillWidth: true
        label: qsTr("Preset")
        Row {
            spacing: 8
            AppComboBox {
                width: 180
                model: presets.names
                currentIndex: presets.selectedIndex
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => presets.selectedIndex = index
            }
            Button {
                text: qsTr("Apply")
                font.pixelSize: Theme.fontSizeSmall
                enabled: presets.hasPresets
                onClicked: presets.applySelected()
            }
            Button {
                text: qsTr("Delete")
                font.pixelSize: Theme.fontSizeSmall
                enabled: presets.hasPresets
                onClicked: presets.deleteSelected()
            }
        }
    }

    FieldRow {
        Layout.fillWidth: true
        label: qsTr("Save preset")
        Row {
            spacing: 8
            TextField {
                width: 180
                placeholderText: qsTr("Preset name")
                text: presets.newName
                font.pixelSize: Theme.fontSizeSmall
                selectByMouse: true
                onTextEdited: presets.newName = text
            }
            Button {
                text: qsTr("Save")
                font.pixelSize: Theme.fontSizeSmall
                onClicked: presets.saveCurrent()
            }
        }
    }

    Text {
        visible: presets.statusText.length > 0
        Layout.fillWidth: true
        text: presets.statusText
        font.pixelSize: Theme.fontSizeCaption
        color: Theme.muted
        wrapMode: Text.Wrap
    }

    // -- Transcript (Whisper) ------------------------------------------------
    AccordionHeader {
        Layout.fillWidth: true
        title: qsTr("Transcript (Whisper)")
        expanded: root.transcriptExpanded
        onToggled: root.transcriptExpanded = !root.transcriptExpanded
    }

    ColumnLayout {
        visible: root.transcriptExpanded
        Layout.fillWidth: true
        spacing: 6

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Whisper model")
            AppComboBox {
                width: 160
                model: jobForm.whisperModels
                currentIndex: jobForm.whisperModels.indexOf(jobForm.whisperModel)
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => jobForm.whisperModel = currentValue
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Segment length")
            AppComboBox {
                width: 260
                model: jobForm.segmentLabels
                currentIndex: jobForm.segmentIndex
                font.pixelSize: Theme.fontSizeSmall
                ToolTip.visible: hovered
                ToolTip.delay: 400
                ToolTip.text: qsTr("Overrides the global default from Settings for this job")
                onActivated: (index) => jobForm.segmentIndex = index
            }
        }

        CheckBox {
            Layout.fillWidth: true
            text: qsTr("Filter Whisper hallucinations (silence, loops, boilerplate)")
            checked: jobForm.transcriptFilter
            onToggled: jobForm.transcriptFilter = checked
            font.pixelSize: Theme.fontSizeSmall
            ToolTip.visible: hovered
            ToolTip.delay: 400
            ToolTip.text: qsTr("Drops hallucinated segments using Whisper probabilities and a boilerplate list. The raw transcript is kept as *.raw.* plus transcript_filter_report.json.")
        }
    }

    // -- AI analysis ---------------------------------------------------------
    AccordionHeader {
        Layout.fillWidth: true
        title: qsTr("AI analysis")
        expanded: root.aiExpanded
        onToggled: root.aiExpanded = !root.aiExpanded
    }

    ColumnLayout {
        visible: root.aiExpanded
        Layout.fillWidth: true
        spacing: 6

        CheckBox {
            text: qsTr("Enable AI analysis (summary and highlights)")
            enabled: jobForm.analysisAllowed
            checked: jobForm.analysisEnabled
            onToggled: jobForm.analysisEnabled = checked
            font.pixelSize: Theme.fontSizeSmall
        }

        CatalogComboBox {
            Layout.fillWidth: true
            vision: false
        }

        CheckBox {
            text: qsTr("Enable AI vision analysis (describe frames)")
            enabled: jobForm.visionAllowed
            checked: jobForm.visionEnabled
            onToggled: jobForm.visionEnabled = checked
            font.pixelSize: Theme.fontSizeSmall
        }

        CatalogComboBox {
            Layout.fillWidth: true
            vision: true
        }
    }

    // -- Visual analysis (vision) -------------------------------------------
    AccordionHeader {
        Layout.fillWidth: true
        title: qsTr("Visual analysis (vision)")
        expanded: root.visualExpanded
        onToggled: root.visualExpanded = !root.visualExpanded
    }

    ColumnLayout {
        visible: root.visualExpanded
        Layout.fillWidth: true
        spacing: 6

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Frame extraction")

            Row {
                spacing: 12
                CheckBox {
                    text: qsTr("Interval")
                    checked: jobForm.intervalMode
                    onToggled: jobForm.intervalMode = checked
                    font.pixelSize: Theme.fontSizeSmall
                }
                CheckBox {
                    text: qsTr("Scene")
                    checked: jobForm.sceneMode
                    onToggled: jobForm.sceneMode = checked
                    font.pixelSize: Theme.fontSizeSmall
                }
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Time interval (seconds)")
            visible: jobForm.intervalMode
            SpinBox {
                width: 90
                from: 1
                to: 3600
                value: jobForm.frameInterval
                editable: true
                onValueModified: jobForm.frameInterval = value
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Scene sensitivity")
            visible: jobForm.sceneMode
            SpinBox {
                width: 90
                from: 5
                to: 95
                stepSize: 5
                value: Math.round(jobForm.sceneSensitivity * 100)
                editable: true
                onValueModified: jobForm.sceneSensitivity = value / 100.0
            }
        }

        FieldRow {
            Layout.fillWidth: true
            label: qsTr("Vision resolution")
            AppComboBox {
                width: 260
                model: jobForm.resolutionLabels
                currentIndex: jobForm.frameResolutionIndex
                font.pixelSize: Theme.fontSizeSmall
                onActivated: (index) => jobForm.frameResolutionIndex = index
            }
        }
    }

    CheckBox {
        Layout.fillWidth: true
        text: qsTr("Generate FullReportAndTimeline.htm with embedded frames")
        checked: jobForm.embedFrames
        onToggled: jobForm.embedFrames = checked
        font.pixelSize: Theme.fontSizeSmall
        ToolTip.visible: hovered
        ToolTip.delay: 400
        ToolTip.text: qsTr("Writes a human-readable FullReportAndTimeline.htm with the summary, highlights, full transcript and frames embedded as base64. The Master Timeline .md stays lean with relative file paths.")
    }
}
