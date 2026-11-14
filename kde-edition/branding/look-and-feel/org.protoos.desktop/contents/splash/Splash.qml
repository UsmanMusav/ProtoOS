import QtQuick 2.15

// Original ProtoOS startup surface. It uses only basic QtQuick primitives so
// it remains reliable in the virtual X11 session and carries no upstream logo.
Rectangle {
    id: root
    color: "#10152f"
    property int stage: 0

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#10152f" }
            GradientStop { position: 0.52; color: "#1a1d4a" }
            GradientStop { position: 1.0; color: "#30245c" }
        }
    }

    Item {
        id: content
        anchors.centerIn: parent
        width: 360
        height: 250
        opacity: root.stage >= 2 ? 1 : 0

        Behavior on opacity {
            NumberAnimation { duration: 240; easing.type: Easing.OutCubic }
        }

        Item {
            id: mark
            anchors.horizontalCenter: parent.horizontalCenter
            y: 18
            width: 84
            height: 84

            Rectangle {
                x: 12
                y: 4
                width: 24
                height: 76
                radius: 12
                color: "#b8a8ff"
            }
            Rectangle {
                x: 28
                y: 4
                width: 48
                height: 38
                radius: 19
                color: "#7d76ed"
            }
            Rectangle {
                x: 28
                y: 17
                width: 26
                height: 13
                radius: 6
                color: "#23234d"
            }
            Rectangle {
                x: 0
                y: 61
                width: 15
                height: 15
                radius: 7.5
                color: "#84e3d5"
            }
        }

        Text {
            anchors.top: mark.bottom
            anchors.topMargin: 18
            anchors.horizontalCenter: parent.horizontalCenter
            text: "ProtoOS"
            color: "#f5f3ff"
            font.pixelSize: 32
            font.weight: Font.DemiBold
            letterSpacing: 1.1
        }

        Text {
            anchors.top: mark.bottom
            anchors.topMargin: 62
            anchors.horizontalCenter: parent.horizontalCenter
            text: Qt.locale().name.indexOf("ru") === 0 ? "Подготавливаем рабочее пространство" : "Preparing your workspace"
            color: "#c9c5f4"
            font.pixelSize: 14
        }

        Row {
            anchors.top: mark.bottom
            anchors.topMargin: 100
            anchors.horizontalCenter: parent.horizontalCenter
            spacing: 9

            Repeater {
                model: 3
                delegate: Rectangle {
                    width: 8
                    height: 8
                    radius: 4
                    color: "#9c94ff"
                    opacity: pulse.activeIndex === index ? 1 : 0.3
                }
            }
        }
    }

    Timer {
        id: pulse
        property int activeIndex: 0
        interval: 260
        running: root.stage >= 2
        repeat: true
        onTriggered: activeIndex = (activeIndex + 1) % 3
    }
}
