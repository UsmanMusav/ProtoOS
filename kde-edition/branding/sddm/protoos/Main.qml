import QtQuick 2.15
import SddmComponents 2.0

// ProtoOS sign-in surface. Autologin normally reaches the desktop immediately,
// but this remains a complete usable path after logout or if autologin is off.
Rectangle {
    id: root
    width: 1280
    height: 720
    color: "#10152f"

    property int sessionIndex: sessionSelector.index
    property bool russian: Qt.locale().name.indexOf("ru") === 0

    Connections {
        target: sddm
        function onLoginFailed() {
            passwordEntry.text = ""
            passwordEntry.focus = true
        }
    }

    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: "#0e1430" }
            GradientStop { position: 0.48; color: "#1a1d4a" }
            GradientStop { position: 1.0; color: "#382760" }
        }
    }

    // Quiet aurora light bands; they are shapes, not a copied wallpaper.
    Rectangle {
        width: parent.width * 0.75
        height: parent.width * 0.75
        radius: width / 2
        x: -width * 0.38
        y: -height * 0.55
        color: "#6057b7"
        opacity: 0.17
    }
    Rectangle {
        width: parent.width * 0.58
        height: parent.width * 0.58
        radius: width / 2
        x: parent.width - width * 0.42
        y: parent.height - height * 0.37
        color: "#78d8d0"
        opacity: 0.12
    }

    Column {
        id: identity
        anchors.left: parent.left
        anchors.leftMargin: Math.max(48, parent.width * 0.14)
        anchors.verticalCenter: parent.verticalCenter
        spacing: 15

        Item {
            width: 92
            height: 92

            Rectangle {
                x: 15
                y: 6
                width: 27
                height: 80
                radius: 13.5
                color: "#c0b3ff"
            }
            Rectangle {
                x: 33
                y: 6
                width: 53
                height: 42
                radius: 21
                color: "#847cf2"
            }
            Rectangle {
                x: 33
                y: 21
                width: 29
                height: 14
                radius: 7
                color: "#24234d"
            }
            Rectangle {
                x: 0
                y: 68
                width: 16
                height: 16
                radius: 8
                color: "#87e7d8"
            }
        }

        Text {
            text: "ProtoOS"
            color: "#f7f5ff"
            font.pixelSize: 42
            font.weight: Font.DemiBold
            letterSpacing: 1.3
        }
        Text {
            text: root.russian ? "Ваше пространство для работы" : "Your space to work"
            color: "#cbc8f2"
            font.pixelSize: 18
        }
        Text {
            width: 330
            wrapMode: Text.WordWrap
            text: root.russian ? "Live-сессия запускается без сохранения изменений после выключения." : "This Live session does not keep changes after shutdown."
            color: "#aaa8d7"
            font.pixelSize: 13
            lineHeight: 1.25
        }
    }

    Rectangle {
        id: signInCard
        width: Math.min(390, parent.width - 72)
        height: 348
        anchors.right: parent.right
        anchors.rightMargin: Math.max(40, parent.width * 0.14)
        anchors.verticalCenter: parent.verticalCenter
        radius: 22
        color: "#e9e8ff"
        opacity: 0.98
        border.width: 1
        border.color: "#ffffff"

        Column {
            anchors.fill: parent
            anchors.margins: 32
            spacing: 12

            Text {
                text: root.russian ? "Вход в ProtoOS" : "Sign in to ProtoOS"
                color: "#24234d"
                font.pixelSize: 24
                font.weight: Font.DemiBold
            }
            Text {
                width: parent.width
                text: root.russian ? "Продолжите работу в Live-сессии" : "Continue to the Live session"
                color: "#5b5a83"
                font.pixelSize: 13
            }

            Item { width: 1; height: 4 }

            Text {
                text: root.russian ? "Пользователь" : "User"
                color: "#46466e"
                font.pixelSize: 12
            }
            TextBox {
                id: userEntry
                width: parent.width
                height: 38
                text: userModel.lastUser
                KeyNavigation.tab: passwordEntry
            }

            Text {
                text: root.russian ? "Пароль" : "Password"
                color: "#46466e"
                font.pixelSize: 12
            }
            PasswordBox {
                id: passwordEntry
                width: parent.width
                height: 38
                KeyNavigation.backtab: userEntry
                KeyNavigation.tab: signInButton
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter) {
                        sddm.login(userEntry.text, passwordEntry.text, root.sessionIndex)
                        event.accepted = true
                    }
                }
            }

            Rectangle {
                id: signInButton
                width: parent.width
                height: 42
                radius: 13
                color: signInMouse.pressed ? "#514abb" : "#635bd2"
                focus: true
                KeyNavigation.backtab: passwordEntry
                KeyNavigation.tab: sessionSelector

                Text {
                    anchors.centerIn: parent
                    text: root.russian ? "Продолжить" : "Continue"
                    color: "#ffffff"
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    id: signInMouse
                    anchors.fill: parent
                    onClicked: sddm.login(userEntry.text, passwordEntry.text, root.sessionIndex)
                }
                Keys.onPressed: function(event) {
                    if (event.key === Qt.Key_Return || event.key === Qt.Key_Enter || event.key === Qt.Key_Space) {
                        sddm.login(userEntry.text, passwordEntry.text, root.sessionIndex)
                        event.accepted = true
                    }
                }
            }

            ComboBox {
                id: sessionSelector
                width: parent.width
                height: 30
                model: sessionModel
                index: sessionModel.lastIndex
                KeyNavigation.backtab: signInButton
                KeyNavigation.tab: userEntry
            }
        }
    }

    Row {
        anchors.left: parent.left
        anchors.leftMargin: 28
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        spacing: 22

        Text {
            text: root.russian ? "Выключить" : "Power off"
            color: "#d8d5f7"
            font.pixelSize: 13
            MouseArea { anchors.fill: parent; onClicked: sddm.powerOff() }
        }
        Text {
            text: root.russian ? "Перезагрузить" : "Restart"
            color: "#d8d5f7"
            font.pixelSize: 13
            MouseArea { anchors.fill: parent; onClicked: sddm.reboot() }
        }
    }

    Component.onCompleted: {
        if (userEntry.text === "")
            userEntry.focus = true
        else
            passwordEntry.focus = true
    }
}
