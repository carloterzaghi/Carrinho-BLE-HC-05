import tkinter as tk
import tkinter.font as tkfont
from tkinter import ttk, messagebox
import re
import socket
import subprocess
import asyncio
import threading

try:
    from bleak import BleakClient
except ImportError:
    BleakClient = None

# Canal RFCOMM padrão do HC-05 (SPP)
RFCOMM_CHANNEL = 1

# Característica BLE padrão de módulos serial (HM-10 / HC-08 / HC-05 BLE)
BLE_PREFERRED_CHAR = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Lista dispositivos Bluetooth pareados no Windows (clássicos e BLE)
PS_LIST_DEVICES = (
    "Get-PnpDevice -Class Bluetooth | "
    "Where-Object { $_.InstanceId -like 'BTHENUM\\DEV_*' -or $_.InstanceId -like 'BTHLE\\DEV_*' } | "
    "ForEach-Object { $_.FriendlyName + '|' + $_.InstanceId }"
)


class BleConnection:
    """Conexão BLE com interface parecida com socket (sendall/close)."""

    def __init__(self, address):
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.thread.start()
        self.client = BleakClient(address)
        self.char = None
        try:
            self._run(self._connect(), 20)
        except Exception:
            self.close()
            raise

    def _run(self, coro, timeout):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    async def _connect(self):
        await self.client.connect()
        chars = [c for s in self.client.services for c in s.characteristics]
        writable = [
            c for c in chars
            if "write" in c.properties or "write-without-response" in c.properties
        ]
        if not writable:
            raise RuntimeError("Nenhuma característica de escrita encontrada.")
        self.char = next(
            (c for c in writable if c.uuid.lower() == BLE_PREFERRED_CHAR),
            writable[0]
        )

    async def _write(self, data):
        response = "write-without-response" not in self.char.properties
        await self.client.write_gatt_char(self.char, data, response=response)

    def sendall(self, data):
        self._run(self._write(data), 5)

    def close(self):
        try:
            self._run(self.client.disconnect(), 5)
        except Exception:
            pass
        self.loop.call_soon_threadsafe(self.loop.stop)


class BluetoothController:
    def __init__(self, root):
        self.root = root
        self.root.title("Controle Arduino - HC-05")
        # Janela proporcional à tela do usuário, centralizada
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        win_h = int(screen_h * 0.8)
        win_w = min(int(screen_w * 0.9), int(win_h * 0.85))
        x = (screen_w - win_w) // 2
        y = (screen_h - win_h) // 2
        self.root.geometry(f"{win_w}x{win_h}+{x}+{y}")
        self.root.minsize(380, 520)

        self.serial_connection = None

        # Fontes que escalam com o tamanho da janela
        self.title_font = tkfont.Font(family="Arial", size=22, weight="bold")
        self.arrow_font = tkfont.Font(family="Arial", size=28, weight="bold")
        self.stop_font = tkfont.Font(family="Arial", size=16, weight="bold")
        self.root.bind("<Configure>", self.on_resize)

        # =========================
        # TÍTULO
        # =========================

        title = tk.Label(
            root,
            text="Controle Bluetooth",
            font=self.title_font
        )
        title.pack(pady=(20, 5))

        subtitle = tk.Label(
            root,
            text="Arduino Uno + HC-05",
            font=("Arial", 11)
        )
        subtitle.pack()

        # =========================
        # SELEÇÃO DA PORTA
        # =========================

        connection_frame = tk.LabelFrame(
            root,
            text="Conexão",
            padx=15,
            pady=15
        )
        connection_frame.pack(
            padx=20,
            pady=20,
            fill="x"
        )

        tk.Label(
            connection_frame,
            text="Dispositivo HC-05:"
        ).grid(row=0, column=0, padx=5, pady=5)

        connection_frame.columnconfigure(1, weight=1)

        self.port_combo = ttk.Combobox(
            connection_frame,
            state="readonly"
        )
        self.port_combo.grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
            sticky="ew"
        )

        refresh_button = tk.Button(
            connection_frame,
            text="Atualizar",
            command=self.refresh_ports
        )
        refresh_button.grid(
            row=1,
            column=0,
            columnspan=2,
            pady=8
        )

        self.connect_button = tk.Button(
            connection_frame,
            text="Conectar",
            width=15,
            command=self.toggle_connection
        )
        self.connect_button.grid(
            row=2,
            column=0,
            columnspan=2,
            pady=5
        )

        # =========================
        # STATUS
        # =========================

        self.status_label = tk.Label(
            root,
            text="● Desconectado",
            font=("Arial", 12, "bold"),
            fg="red"
        )
        self.status_label.pack(pady=5)

        # =========================
        # CONTROLE
        # =========================

        control_frame = tk.LabelFrame(
            root,
            text="Controle",
            padx=20,
            pady=20
        )
        control_frame.pack(
            padx=20,
            pady=15,
            fill="both",
            expand=True
        )

        for i in range(3):
            control_frame.columnconfigure(i, weight=1, uniform="c")
            control_frame.rowconfigure(i, weight=1, uniform="r")

        # FRENTE
        self.up_button = tk.Button(
            control_frame,
            text="↑",
            font=self.arrow_font
        )
        self.up_button.grid(
            row=0,
            column=1,
            padx=5,
            pady=5,
            sticky="nsew"
        )

        # ESQUERDA
        self.left_button = tk.Button(
            control_frame,
            text="←",
            font=self.arrow_font
        )
        self.left_button.grid(
            row=1,
            column=0,
            padx=5,
            pady=5,
            sticky="nsew"
        )

        # STOP
        self.stop_button = tk.Button(
            control_frame,
            text="STOP",
            font=self.stop_font,
            command=lambda: self.send_command("S")
        )
        self.stop_button.grid(
            row=1,
            column=1,
            padx=5,
            pady=5,
            sticky="nsew"
        )

        # DIREITA
        self.right_button = tk.Button(
            control_frame,
            text="→",
            font=self.arrow_font
        )
        self.right_button.grid(
            row=1,
            column=2,
            padx=5,
            pady=5,
            sticky="nsew"
        )

        # RÉ
        self.down_button = tk.Button(
            control_frame,
            text="↓",
            font=self.arrow_font
        )
        self.down_button.grid(
            row=2,
            column=1,
            padx=5,
            pady=5,
            sticky="nsew"
        )

        # =========================
        # ÚLTIMO COMANDO
        # =========================

        self.command_label = tk.Label(
            root,
            text="Último comando: -",
            font=("Arial", 12)
        )
        self.command_label.pack(
            side="bottom",
            pady=10,
            before=control_frame
        )

        # =========================
        # CONFIGURAÇÃO DOS BOTÕES
        # =========================

        # Pressionar botão
        self.up_button.bind(
            "<ButtonPress-1>",
            lambda event: self.send_command("U")
        )
        self.down_button.bind(
            "<ButtonPress-1>",
            lambda event: self.send_command("D")
        )
        self.left_button.bind(
            "<ButtonPress-1>",
            lambda event: self.send_command("L")
        )
        self.right_button.bind(
            "<ButtonPress-1>",
            lambda event: self.send_command("R")
        )

        # Soltar botão = STOP
        self.up_button.bind(
            "<ButtonRelease-1>",
            lambda event: self.send_command("S")
        )
        self.down_button.bind(
            "<ButtonRelease-1>",
            lambda event: self.send_command("S")
        )
        self.left_button.bind(
            "<ButtonRelease-1>",
            lambda event: self.send_command("S")
        )
        self.right_button.bind(
            "<ButtonRelease-1>",
            lambda event: self.send_command("S")
        )

        # =========================
        # TECLADO
        # =========================

        self.root.bind("<KeyPress-Up>", self.key_press)
        self.root.bind("<KeyPress-Down>", self.key_press)
        self.root.bind("<KeyPress-Left>", self.key_press)
        self.root.bind("<KeyPress-Right>", self.key_press)

        self.root.bind("<KeyRelease-Up>", self.key_release)
        self.root.bind("<KeyRelease-Down>", self.key_release)
        self.root.bind("<KeyRelease-Left>", self.key_release)
        self.root.bind("<KeyRelease-Right>", self.key_release)

        self.root.bind("<space>", lambda event: self.send_command("S"))

        # Atualiza portas ao iniciar
        self.refresh_ports()

        # Fecha corretamente
        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close
        )

    def on_resize(self, event):

        if event.widget is not self.root:
            return

        scale = min(event.width / 450, event.height / 650)

        self.title_font.configure(size=max(14, int(22 * scale)))
        self.arrow_font.configure(size=max(14, int(28 * scale)))
        self.stop_font.configure(size=max(10, int(16 * scale)))

    # ==================================================
    # DISPOSITIVOS BLUETOOTH PAREADOS
    # ==================================================

    def refresh_ports(self):

        devices = {}
        self.device_types = {}

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", PS_LIST_DEVICES],
                capture_output=True,
                text=True,
                timeout=15,
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            for line in result.stdout.splitlines():
                name, _, instance_id = line.partition("|")
                match = re.search(r"DEV_([0-9A-Fa-f]{12})", instance_id)

                if match:
                    mac = match.group(1).upper()
                    mac = ":".join(mac[i:i + 2] for i in range(0, 12, 2))
                    devices[mac] = name.strip()
                    self.device_types[mac] = (
                        "ble" if instance_id.startswith("BTHLE") else "classic"
                    )

        except Exception as e:
            print(f"Erro ao listar dispositivos: {e}")

        device_list = [
            f"{name} - {mac}" for mac, name in devices.items()
        ]

        self.port_combo["values"] = device_list

        if device_list:
            self.port_combo.current(0)

    # ==================================================
    # CONECTAR / DESCONECTAR
    # ==================================================

    def toggle_connection(self):

        if self.serial_connection is not None:
            self.disconnect()
        else:
            self.connect()

    def connect(self):

        selected = self.port_combo.get()

        if not selected:
            messagebox.showwarning(
                "Atenção",
                "Selecione o dispositivo HC-05 pareado."
            )
            return

        # Pega somente o endereço MAC
        address = selected.rsplit(" - ", 1)[1]

        try:

            if self.device_types.get(address) == "ble":
                if BleakClient is None:
                    raise RuntimeError(
                        "Dispositivo BLE: instale a biblioteca com 'pip install bleak'."
                    )
                connection = BleConnection(address)
            else:
                connection = socket.socket(
                    socket.AF_BLUETOOTH,
                    socket.SOCK_STREAM,
                    socket.BTPROTO_RFCOMM
                )
                connection.settimeout(10)
                connection.connect((address, RFCOMM_CHANNEL))
                connection.settimeout(1)

            self.serial_connection = connection

            self.status_label.config(
                text="● Conectado",
                fg="green"
            )

            self.connect_button.config(
                text="Desconectar"
            )

            self.send_command("S")

        except Exception as e:

            self.serial_connection = None

            messagebox.showerror(
                "Erro de conexão",
                f"Não foi possível conectar.\n\n{e}"
            )

    def disconnect(self):

        if self.serial_connection:

            try:
                self.send_command("S")
                self.serial_connection.close()
            except:
                pass

        self.serial_connection = None

        self.status_label.config(
            text="● Desconectado",
            fg="red"
        )

        self.connect_button.config(
            text="Conectar"
        )

    # ==================================================
    # ENVIA COMANDO
    # ==================================================

    def send_command(self, command):

        if self.serial_connection is None:
            return

        try:

            self.serial_connection.sendall(
                command.encode()
            )

            self.command_label.config(
                text=f"Último comando: {command}"
            )

        except Exception as e:

            print(
                f"Erro ao enviar comando: {e}"
            )

    # ==================================================
    # TECLADO
    # ==================================================

    def key_press(self, event):

        commands = {
            "Up": "U",
            "Down": "D",
            "Left": "L",
            "Right": "R"
        }

        command = commands.get(event.keysym)

        if command:
            self.send_command(command)

    def key_release(self, event):

        if event.keysym in [
            "Up",
            "Down",
            "Left",
            "Right"
        ]:
            self.send_command("S")

    # ==================================================
    # FECHAR PROGRAMA
    # ==================================================

    def close(self):

        self.disconnect()
        self.root.destroy()


# ======================================================
# INICIA PROGRAMA
# ======================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = BluetoothController(root)

    root.mainloop()
