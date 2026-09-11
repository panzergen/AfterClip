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
            ComboBox {
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
            ComboBox {
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
            ComboBox {
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
