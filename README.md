# ProtoOS Live

**ProtoOS** — учебная Linux Live-система `x86_64`: Linux запускает статический BusyBox из initramfs и открывает консоль `ProtoOS#`. Установка на диск гостя не выполняется.

> Это тестовая сборка. Не используйте её для данных или повседневной работы.

## Hyper-V: VHD 0.3.0

Для Hyper-V используется fixed VHD с GPT и EFI System Partition:

```text
ProtoOS-HyperV-0.3.0.vhd
```

Внутри находятся Limine 8.7.0, настоящее VFAT-длинное имя `limine.conf`, initramfs и отдельное Linux 6.1.0 EFI-stub ядро. Оно собрано с драйверами гостя Microsoft Hyper-V, EFI early console, EFI framebuffer и framebuffer console. Это заменяет прежнее стороннее ядро, в котором отсутствовала необходимая конфигурация консоли — поэтому после выбора пункта Limine пользователь видел только чёрный экран.

Меню Limine остаётся на экране. Выберите:

```text
ProtoOS Hyper-V Live 0.3.0 (Hyper-V console)
```

и нажмите **Enter**. Ядро получает `earlycon=efi,keep`, `console=tty0` и подробное логирование; его вывод и последующее приглашение должны быть видны в окне Hyper-V.

## Запуск в Hyper-V (русская локализация)

1. Полностью выключите ВМ.
2. В **Параметры → Контроллер SCSI → Жесткий диск** удалите старый VHD и подключите `ProtoOS-HyperV-0.3.0.vhd`.
3. В **Параметры → Встроенное ПО** поставьте **Жесткий диск** первым.
4. В **Параметры → Безопасность** снимите флажок **Включить безопасную загрузку**.
5. ВМ должна быть **Поколение 2**. DVD/ISO отключите.
6. Запустите ВМ, выберите пункт ProtoOS в Limine и нажмите **Enter**.

Ожидаемое приглашение:

```text
ProtoOS#
```

Для проверки: `help`, `sysinfo`, `uname -a`, `cat /etc/os-release`, `poweroff`.

## Локальная сборка и проверки

Требуются `python3`, `git` и статический BusyBox в `/usr/bin/busybox`.

```sh
make vhd
make check-vhd
```

`make check-vhd` проверяет fixed VHD footer, MBR/GPT, FAT16 ESP, Limine, Linux EFI-stub и gzip initramfs.

## Происхождение компонентов

| Компонент | Источник / версия | SHA-256 |
| --- | --- | --- |
| Hyper-V Linux EFI-stub | Linux 6.1.0 (`torvalds/linux` `7614896350aa20764c5eca527262d9eb0a57da63`), конфигурация на основе WSL 6.1 с включёнными Hyper-V/EFI-console/framebuffer драйверами | `59ee81bedc390ef83f3b1c6f334419ff404d49b10817ae20670036061f9e5a7d` |
| Limine EFI | limine-bootloader/limine, `aad3edd370955449717a334f0289dee10e2c5f01` | `51ca2b20ed14bbc678a396cdfb0c1d941acbc155cabebc9bfafabe4cdae1be73` |
| Experimental ISO Linux EFI-stub | RedMoonnn/MicroLinux, `00a515d49c59f31c9c5e258928ac368012ac1ea6` | `dca8ba50d3ac9867073b54b7d694d019c9e048560102ddd4f9b2563df00686fd` |

## Ограничения

Только Hyper-V Generation 2 и x86_64 UEFI; Secure Boot, сеть и сохранение данных пока не поддерживаются. Графическая **ProtoOS KDE Edition** развивается как отдельный Debian/KDE проект в [`kde-edition/`](kde-edition/); актуальные тестовые VHD доступны на [странице релизов](https://github.com/UsmanMusav/ProtoOS/releases). Выбранное направление интерфейса и требования к отзывчивости Hyper-V описаны в [`kde-edition/DESIGN_DIRECTION.md`](kde-edition/DESIGN_DIRECTION.md). Старые ISO и VHD 0.2.x — устаревшие диагностические варианты.
