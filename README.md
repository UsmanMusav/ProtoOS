# ProtoOS Live

**ProtoOS** — учебная минимальная Live-система на Linux для `x86_64`. Версия **0.1.2** загружается в оперативную память, запускает BusyBox и даёт интерактивную консоль. На диск гостевой машины ничего не устанавливается.

> Это ранняя тестовая сборка, а не система для повседневного использования или хранения данных.

## Важно: исправление Hyper-V в 0.1.2

Тесты образов 0.1.0 и 0.1.1 в Hyper-V завершались до запуска загрузчика сообщением **“The boot loader did not load an operating system”**. Это дефект раннего ISO: собственный FAT El Torito-образ не являлся тем форматом UEFI CD, который ожидает прошивка Hyper-V.

В 0.1.2 применена стандартная загрузочная цепочка Limine:

- официальный `limine-uefi-cd.bin` — FAT12 El Torito UEFI CD image;
- Limine 8.7.0 читает `LIMINE.CONF`, ядро и initramfs непосредственно из ISO-9660;
- в каталоге El Torito есть и начальная UEFI-запись, и UEFI section entry для совместимости прошивок.

Используйте **только** `ProtoOS-0.1.2-x86_64.iso` для следующего теста.

## Что уже работает

- загрузка через **UEFI** с ISO-образа;
- Limine UEFI boot manager;
- Linux-ядро с EFI stub;
- initramfs в памяти: BusyBox, `/proc`, `/sys`, `/dev`;
- консоль `ProtoOS#` и команды `help`, `sysinfo`, `uname -a`, `poweroff`;
- сборка ISO одним вызовом `make iso` без GRUB, xorriso или mtools.

## Быстрый старт для тестера: Hyper-V

1. Возьмите файл `dist/ProtoOS-0.1.2-x86_64.iso` из готовой сборки.
2. Полностью **выключите** старую виртуальную машину.
3. В **SCSI Controller → DVD Drive** удалите старый ISO и подключите новый.
4. ВМ должна быть **поколения 2** (Generation 2).
5. В **Security** снимите флажок **Enable Secure Boot**.
   - Образ пока не подписан Microsoft-ключом.
6. В **Firmware** поставьте **DVD Drive** первым устройством загрузки.
7. Запустите ВМ. Сначала кратко появится Limine, затем приглашение `ProtoOS#`.

Первые команды для проверки:

```sh
help
sysinfo
uname -a
cat /etc/os-release
ls /
poweroff
```

## Сборка

Требования на машине сборки:

- Linux `x86_64`;
- `python3` и `git`;
- статический BusyBox по пути `/usr/bin/busybox`.

```sh
make iso
make check
```

Готовый ISO появится здесь:

```text
dist/ProtoOS-0.1.2-x86_64.iso
```

`make check` проверяет ISO-9660, начальную и section UEFI El Torito-записи, Limine FAT12 CD image, файлы `LIMINE.CONF`, `KERNEL.EFI` и `INITRD.IMG`.

## Проверяемые внешние компоненты

Сборщик получает и сверяет SHA-256 двух зафиксированных бинарных входов:

| Компонент | Источник | Commit | SHA-256 |
| --- | --- | --- | --- |
| Linux EFI stub | [RedMoonnn/MicroLinux](https://github.com/RedMoonnn/MicroLinux) | `00a515d49c59f31c9c5e258928ac368012ac1ea6` | `dca8ba50d3ac9867073b54b7d694d019c9e048560102ddd4f9b2563df00686fd` |
| Limine UEFI CD image | [limine-bootloader/limine](https://github.com/limine-bootloader/limine) | `aad3edd370955449717a334f0289dee10e2c5f01` | `0ea0aa408c464014a306840acc843dc564e54f602b2077852ceb34178488bd03` |

Это временное решение для быстрой тестовой сборки. Следующая важная задача проекта — воспроизводимая самостоятельная сборка и обновление ядра, затем подпись Secure Boot.

## Что сообщать при ошибке

Пожалуйста, укажите:

1. версию Windows и Hyper-V;
2. поколение ВМ и состояние Secure Boot;
3. сколько памяти выделено;
4. фото/текст последней строки на экране;
5. видите ли экран Limine или kernel panic;
6. появляется ли `ProtoOS#` и выполняется ли `sysinfo`.

## Ограничения 0.1.2

- только `x86_64 UEFI` и Hyper-V Generation 2;
- только английская консоль и минимальный набор BusyBox;
- нет установки на диск, сети, графической оболочки, пользователей или сохранения данных;
- Secure Boot пока не поддерживается;
- запуск на физическом компьютере не является целью этой версии.
