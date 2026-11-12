/*
 * ProtoOS UEFI chain loader.
 *
 * The firmware launches this program as EFI/BOOT/BOOTX64.EFI.  It reads the
 * Linux EFI-stub kernel located beside it, supplies an initrd command line,
 * and transfers control to the kernel.
 *
 * This intentionally uses a very small, self-contained subset of UEFI so the
 * ProtoOS bootstrap does not need a prebuilt third-party boot manager.
 */
#include <stdint.h>
#include <stddef.h>

typedef uint8_t  UINT8;
typedef uint16_t UINT16;
typedef uint32_t UINT32;
typedef uint64_t UINT64;
typedef UINT64   UINTN;
typedef UINT16   CHAR16;
typedef void    *EFI_HANDLE;
typedef UINTN    EFI_STATUS;
typedef UINT32   EFI_MEMORY_TYPE;
typedef UINT8    BOOLEAN;
typedef int16_t  INT16;

typedef struct {
    UINT32 Data1;
    UINT16 Data2;
    UINT16 Data3;
    UINT8 Data4[8];
} EFI_GUID;

typedef struct {
    UINT64 Signature;
    UINT32 Revision;
    UINT32 HeaderSize;
    UINT32 CRC32;
    UINT32 Reserved;
} EFI_TABLE_HEADER;

typedef struct EFI_SYSTEM_TABLE EFI_SYSTEM_TABLE;
typedef struct EFI_BOOT_SERVICES EFI_BOOT_SERVICES;
typedef struct EFI_FILE_PROTOCOL EFI_FILE_PROTOCOL;
typedef struct EFI_SIMPLE_FILE_SYSTEM_PROTOCOL EFI_SIMPLE_FILE_SYSTEM_PROTOCOL;
typedef struct EFI_LOADED_IMAGE_PROTOCOL EFI_LOADED_IMAGE_PROTOCOL;
typedef struct EFI_DEVICE_PATH_PROTOCOL EFI_DEVICE_PATH_PROTOCOL;

#define EFIAPI __attribute__((ms_abi))
#define EFI_SUCCESS 0
#define EFI_LOAD_ERROR 0x8000000000000001ULL
#define EFI_NOT_FOUND  0x800000000000000eULL
#define EFI_FILE_MODE_READ 0x0000000000000001ULL
#define EFI_LOADER_DATA 4

typedef EFI_STATUS (EFIAPI *EFI_TEXT_RESET)(void *This, BOOLEAN ExtendedVerification);
typedef EFI_STATUS (EFIAPI *EFI_TEXT_STRING)(void *This, CHAR16 *String);

typedef struct {
    EFI_TEXT_RESET Reset;
    EFI_TEXT_STRING OutputString;
    void *TestString;
    void *QueryMode;
    void *SetMode;
    void *SetAttribute;
    void *ClearScreen;
    void *SetCursorPosition;
    void *EnableCursor;
    void *Mode;
} EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL;

struct EFI_SYSTEM_TABLE {
    EFI_TABLE_HEADER Hdr;
    CHAR16 *FirmwareVendor;
    UINT32 FirmwareRevision;
    EFI_HANDLE ConsoleInHandle;
    void *ConIn;
    EFI_HANDLE ConsoleOutHandle;
    EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *ConOut;
    EFI_HANDLE StandardErrorHandle;
    EFI_SIMPLE_TEXT_OUTPUT_PROTOCOL *StdErr;
    void *RuntimeServices;
    EFI_BOOT_SERVICES *BootServices;
    UINTN NumberOfTableEntries;
    void *ConfigurationTable;
};

typedef EFI_STATUS (EFIAPI *EFI_HANDLE_PROTOCOL)(EFI_HANDLE Handle, EFI_GUID *Protocol, void **Interface);
typedef EFI_STATUS (EFIAPI *EFI_ALLOCATE_POOL)(EFI_MEMORY_TYPE PoolType, UINTN Size, void **Buffer);
typedef EFI_STATUS (EFIAPI *EFI_FREE_POOL)(void *Buffer);
typedef EFI_STATUS (EFIAPI *EFI_LOAD_IMAGE)(BOOLEAN BootPolicy, EFI_HANDLE ParentImageHandle,
                                              EFI_DEVICE_PATH_PROTOCOL *DevicePath, void *SourceBuffer,
                                              UINTN SourceSize, EFI_HANDLE *ImageHandle);
typedef EFI_STATUS (EFIAPI *EFI_START_IMAGE)(EFI_HANDLE ImageHandle, UINTN *ExitDataSize,
                                               CHAR16 **ExitData);

struct EFI_BOOT_SERVICES {
    EFI_TABLE_HEADER Hdr;
    void *RaiseTPL;
    void *RestoreTPL;
    void *AllocatePages;
    void *FreePages;
    void *GetMemoryMap;
    EFI_ALLOCATE_POOL AllocatePool;
    EFI_FREE_POOL FreePool;
    void *CreateEvent;
    void *SetTimer;
    void *WaitForEvent;
    void *SignalEvent;
    void *CloseEvent;
    void *CheckEvent;
    void *InstallProtocolInterface;
    void *ReinstallProtocolInterface;
    void *UninstallProtocolInterface;
    EFI_HANDLE_PROTOCOL HandleProtocol;
    void *Reserved;
    void *RegisterProtocolNotify;
    void *LocateHandle;
    void *LocateDevicePath;
    void *InstallConfigurationTable;
    EFI_LOAD_IMAGE LoadImage;
    EFI_START_IMAGE StartImage;
    void *Exit;
    void *UnloadImage;
    void *ExitBootServices;
    void *GetNextMonotonicCount;
    void *Stall;
    void *SetWatchdogTimer;
    void *ConnectController;
    void *DisconnectController;
    void *OpenProtocol;
    void *CloseProtocol;
    void *OpenProtocolInformation;
    void *ProtocolsPerHandle;
    void *LocateHandleBuffer;
    void *LocateProtocol;
    void *InstallMultipleProtocolInterfaces;
    void *UninstallMultipleProtocolInterfaces;
    void *CalculateCrc32;
    void *CopyMem;
    void *SetMem;
    void *CreateEventEx;
};

typedef EFI_STATUS (EFIAPI *EFI_FILE_OPEN)(EFI_FILE_PROTOCOL *This, EFI_FILE_PROTOCOL **NewHandle,
                                             CHAR16 *FileName, UINT64 OpenMode, UINT64 Attributes);
typedef EFI_STATUS (EFIAPI *EFI_FILE_CLOSE)(EFI_FILE_PROTOCOL *This);
typedef EFI_STATUS (EFIAPI *EFI_FILE_READ)(EFI_FILE_PROTOCOL *This, UINTN *BufferSize, void *Buffer);
typedef EFI_STATUS (EFIAPI *EFI_FILE_GET_INFO)(EFI_FILE_PROTOCOL *This, EFI_GUID *InformationType,
                                                 UINTN *BufferSize, void *Buffer);

struct EFI_FILE_PROTOCOL {
    UINT64 Revision;
    EFI_FILE_OPEN Open;
    EFI_FILE_CLOSE Close;
    void *Delete;
    EFI_FILE_READ Read;
    void *Write;
    void *GetPosition;
    void *SetPosition;
    EFI_FILE_GET_INFO GetInfo;
    void *SetInfo;
    void *Flush;
    void *OpenEx;
    void *ReadEx;
    void *WriteEx;
    void *FlushEx;
};

typedef EFI_STATUS (EFIAPI *EFI_OPEN_VOLUME)(EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *This,
                                               EFI_FILE_PROTOCOL **Root);
struct EFI_SIMPLE_FILE_SYSTEM_PROTOCOL {
    UINT64 Revision;
    EFI_OPEN_VOLUME OpenVolume;
};

struct EFI_LOADED_IMAGE_PROTOCOL {
    UINT32 Revision;
    EFI_HANDLE ParentHandle;
    EFI_SYSTEM_TABLE *SystemTable;
    EFI_HANDLE DeviceHandle;
    EFI_DEVICE_PATH_PROTOCOL *FilePath;
    void *Reserved;
    UINT32 LoadOptionsSize;
    void *LoadOptions;
    void *ImageBase;
    UINT64 ImageSize;
    EFI_MEMORY_TYPE ImageCodeType;
    EFI_MEMORY_TYPE ImageDataType;
    void *Unload;
};

typedef struct {
    UINT64 Size;
    UINT64 FileSize;
    UINT64 PhysicalSize;
    struct { UINT16 Year; UINT8 Month, Day, Hour, Minute, Second, Pad1; UINT32 Nanosecond; INT16 TimeZone; UINT8 Daylight, Pad2; } CreateTime;
    struct { UINT16 Year; UINT8 Month, Day, Hour, Minute, Second, Pad1; UINT32 Nanosecond; INT16 TimeZone; UINT8 Daylight, Pad2; } LastAccessTime;
    struct { UINT16 Year; UINT8 Month, Day, Hour, Minute, Second, Pad1; UINT32 Nanosecond; INT16 TimeZone; UINT8 Daylight, Pad2; } ModificationTime;
    UINT64 Attribute;
    CHAR16 FileName[1];
} EFI_FILE_INFO;

/* A valid (absolute-only) PE relocation block lets strict UEFI loaders relocate this PIE. */
static const UINT8 efi_relocation_block[] __attribute__((used, section(".reloc"))) =
    {0, 0, 0, 0, 10, 0, 0, 0, 0, 0};

static EFI_GUID LOADED_IMAGE_PROTOCOL =
    {0x5b1b31a1, 0x9562, 0x11d2, {0x8e, 0x3f, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static EFI_GUID SIMPLE_FILE_SYSTEM_PROTOCOL =
    {0x964e5b22, 0x6459, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};
static EFI_GUID FILE_INFO_GUID =
    {0x09576e92, 0x6d3f, 0x11d2, {0x8e, 0x39, 0x00, 0xa0, 0xc9, 0x69, 0x72, 0x3b}};

static CHAR16 msg_loading[] = {'P','r','o','t','o','O','S',' ', 'L','i','v','e',' ',
                               '0','.','1','.','0','\r','\n','L','o','a','d','i','n','g',' ',
                               'L','i','n','u','x',' ', 'k','e','r','n','e','l','.','.','.','\r','\n',0};
static CHAR16 msg_error[] = {'P','r','o','t','o','O','S',' ', 'b','o','o','t',' ',
                             'e','r','r','o','r','.','\r','\n',0};
static CHAR16 kernel_path[] = {'\\','E','F','I','\\','B','O','O','T','\\',
                               'K','E','R','N','E','L','.','E','F','I',0};
static CHAR16 kernel_options[] = {
    'c','o','n','s','o','l','e','=','t','t','y','0',' ',
    'i','n','i','t','r','d','=','\\','E','F','I','\\','B','O','O','T','\\',
    'I','N','I','T','R','D','.','I','M','G',0
};

static void print(EFI_SYSTEM_TABLE *system_table, CHAR16 *text) {
    if (system_table && system_table->ConOut && system_table->ConOut->OutputString)
        system_table->ConOut->OutputString(system_table->ConOut, text);
}

static EFI_STATUS read_kernel(EFI_BOOT_SERVICES *bs, EFI_HANDLE device,
                              void **buffer, UINTN *size) {
    EFI_STATUS status;
    EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *fs = NULL;
    EFI_FILE_PROTOCOL *root = NULL;
    EFI_FILE_PROTOCOL *kernel = NULL;
    EFI_FILE_INFO *info = NULL;
    UINTN info_size = 0;
    UINTN bytes;

    status = bs->HandleProtocol(device, &SIMPLE_FILE_SYSTEM_PROTOCOL, (void **)&fs);
    if (status != EFI_SUCCESS) return status;
    status = fs->OpenVolume(fs, &root);
    if (status != EFI_SUCCESS) return status;
    status = root->Open(root, &kernel, kernel_path, EFI_FILE_MODE_READ, 0);
    if (status != EFI_SUCCESS) goto close_root;

    status = kernel->GetInfo(kernel, &FILE_INFO_GUID, &info_size, NULL);
    if (status != EFI_SUCCESS && info_size == 0) goto close_kernel;
    status = bs->AllocatePool(EFI_LOADER_DATA, info_size, (void **)&info);
    if (status != EFI_SUCCESS) goto close_kernel;
    status = kernel->GetInfo(kernel, &FILE_INFO_GUID, &info_size, info);
    if (status != EFI_SUCCESS || info->FileSize == 0) goto free_info;

    if (info->FileSize > (UINTN)-1) { status = EFI_LOAD_ERROR; goto free_info; }
    *size = (UINTN)info->FileSize;
    status = bs->AllocatePool(EFI_LOADER_DATA, *size, buffer);
    if (status != EFI_SUCCESS) goto free_info;
    bytes = *size;
    status = kernel->Read(kernel, &bytes, *buffer);
    if (status != EFI_SUCCESS || bytes != *size) {
        bs->FreePool(*buffer);
        *buffer = NULL;
        status = EFI_LOAD_ERROR;
    }

free_info:
    bs->FreePool(info);
close_kernel:
    kernel->Close(kernel);
close_root:
    root->Close(root);
    return status;
}

EFI_STATUS EFIAPI efi_main(EFI_HANDLE image_handle, EFI_SYSTEM_TABLE *system_table) {
    EFI_BOOT_SERVICES *bs = system_table->BootServices;
    EFI_LOADED_IMAGE_PROTOCOL *self = NULL;
    EFI_LOADED_IMAGE_PROTOCOL *kernel_image = NULL;
    EFI_HANDLE kernel_handle = NULL;
    EFI_STATUS status;
    void *kernel_buffer = NULL;
    UINTN kernel_size = 0;

    print(system_table, msg_loading);
    status = bs->HandleProtocol(image_handle, &LOADED_IMAGE_PROTOCOL, (void **)&self);
    if (status != EFI_SUCCESS || !self || !self->DeviceHandle) goto error;

    status = read_kernel(bs, self->DeviceHandle, &kernel_buffer, &kernel_size);
    if (status != EFI_SUCCESS) goto error;

    status = bs->LoadImage(0, image_handle, NULL, kernel_buffer, kernel_size, &kernel_handle);
    if (status != EFI_SUCCESS) goto error;

    status = bs->HandleProtocol(kernel_handle, &LOADED_IMAGE_PROTOCOL, (void **)&kernel_image);
    if (status != EFI_SUCCESS || !kernel_image) goto error;

    /*
     * A buffer-loaded image has no device path.  The Linux EFI stub needs the
     * originating FAT volume to resolve initrd=, so retain our device handle.
     */
    kernel_image->DeviceHandle = self->DeviceHandle;
    kernel_image->LoadOptions = kernel_options;
    kernel_image->LoadOptionsSize = (UINT32)(sizeof(kernel_options));

    status = bs->StartImage(kernel_handle, NULL, NULL);
    if (status == EFI_SUCCESS) return EFI_SUCCESS;

error:
    print(system_table, msg_error);
    return status == EFI_SUCCESS ? EFI_LOAD_ERROR : status;
}
