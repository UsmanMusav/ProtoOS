# ProtoOS Live

**ProtoOS** — учебная минимальная Live-система на Linux для `x86_64`. Она запускает BusyBox в памяти и даёт интерактивную консоль `ProtoOS#`. На диск гостевой машины ничего не устанавливается.

> Это ранняя тестовая сборка, а не система для повседневного использования или хранения данных.

## Hyper-V: рекомендуемый образ 0.2.1 VHD

Ранние ISO (`0.1.0`–`0.1.3`) предназначались для отладки UEFI CD boot и не проходят загрузку на использованной прошивке Hyper-V. Чтобы не зависеть от особенностей El Torito/оптического привода, для Hyper-V подготовлен отдельный образ:

```text
ProtoOS-HyperV-0.2.1.vhd
```

Это **fixed VHD** с нормальной GPT-разметкой и EFI System Partition. В ESP находятся:

- `/EFI/BOOT/BOOTX64.EFI` — Limine 8.7.0;
- `LIMINE.CONF` — конфигурация загрузки нового формата Limine 8;
- Linux EFI-stub kernel;
- initramfs с BusyBox.

Hyper-V подключает VHD как обычный виртуальный диск, поэтому не нужен DVD boot prompt и не используется нестабильная загрузка с самодельного ISO. В 0.2.1 конфигурация записана под настоящим длинным именем `limine.conf`; это включает новый формат конфигурации Limine 8 и устраняет предупреждение/сообщение `config file contains no valid entries` из 0.2.0.

## Запуск VHD в Hyper-V

1. Полностью **выключите** виртуальную машину.
2. Откройте **Settings → SCSI Controller → Hard Drive**.
3. Если там есть пустой старый VHDX, нажмите **Remove**.
4. Нажмите **Add**, выберите **Hard Drive** и укажите файл `ProtoOS-HyperV-0.2.1.vhd`.
5. Откройте **Settings → Firmware** и поставьте **Hard Drive** на первое место.
6. В **Settings → Security** выключите **Enable Secure Boot**.
7. ВМ должна быть **Generation 2**.
8. Запустите ВМ.

Для этого способа DVD и ISO не нужны. Можно отключить DVD Drive или извлечь из него ISO.

Ожидаемый результат: появится Limine, затем экран ProtoOS и приглашение:

```text
ProtoOS#
```

Первые команды для проверки:

```sh
help
sysinfo
uname -a
cat /etc/os-release
ls /
poweroff
```

## ISO 0.1.3

`ProtoOS-0.1.3-x86_64.iso` сохраняется как экспериментальный ISO-артефакт и проходит структурную проверку ISO-9660, El Torito, FAT12, MBR и GPT. Но для Hyper-V используйте VHD до тех пор, пока CD-загрузка не будет проверена на реальном Hyper-V.

## Локальная сборка

Требования:

- Linux `x86_64`;
- `python3` и `git`;
- статический BusyBox по пути `/usr/bin/busybox`.

```sh
make vhd
make check-vhd
```

или для экспериментального ISO:

```sh
make iso
make check
```

## Автоматическая проверка VHD

`make check-vhd` проверяет:

- формат fixed VHD и контрольную сумму footer;
- защитный MBR;
- primary GPT и CRC таблицы разделов;
- EFI System Partition FAT16;
- обязательные EFI, Limine, kernel и initramfs файлы.

## Проверяемые внешние компоненты

Сборщик получает и сверяет SHA-256 зафиксированных бинарных входов:

| Компонент | Источник | Commit | SHA-256 |
| --- | --- | --- | --- |
| Linux EFI stub | [RedMoonnn/MicroLinux](https://github.com/RedMoonnn/MicroLinux) | `00a515d49c59f31c9c5e258928ac368012ac1ea6` | `dca8ba50d3ac9867073b54b7d694d019c9e048560102ddd4f9b2563df00686fd` |
| Limine EFI application | [limine-bootloader/limine](https://github.com/limine-bootloader/limine) | `aad3edd370955449717a334f0289dee10e2c5f01` | `51ca2b20ed14bbc678a396cdfb0c1d941acbc155cabebc9bfafabe4cdae1be73` |

## Ограничения 0.2.1

- только `x86_64 UEFI` и Hyper-V Generation 2;
- только английская консоль и минимальный набор BusyBox;
- нет установки на диск, сети, графической оболочки, пользователей или сохранения данных;
- Secure Boot пока не поддерживается;
- запуск на физическом компьютере не является целью этой версии.
