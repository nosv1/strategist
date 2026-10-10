import time
import tkinter as tk
from tkinter import ttk

from PyAccUdpInterface.PyAccUdpInterface import accUpdInterface


class GuiInterface:

    def __init__(self, root: tk.Tk, aui: accUpdInterface):
        self.root = root
        self.aui = aui
        self.root.title("ACC UDP Interface")

        self.tree = ttk.Treeview(
            root,
            columns=(
                "Position",
                "Car Number",
                "Driver",
                "Lap",
                "Gear",
                "KPH",
                "Delta",
                "Current Lap",
                "Last Lap",
                "Best Session Lap",
            ),
            show="headings",
        )
        self.tree.heading("Position", text="Position")
        self.tree.heading("Car Number", text="Car Number")
        self.tree.heading("Driver", text="Driver")
        self.tree.heading("Lap", text="Lap")
        self.tree.heading("Gear", text="Gear")
        self.tree.heading("KPH", text="KPH")
        self.tree.heading("Delta", text="Delta")
        self.tree.heading("Current Lap", text="Current Lap")
        self.tree.heading("Last Lap", text="Last Lap")
        self.tree.heading("Best Session Lap", text="Best Session Lap")

        self.tree.pack(fill=tk.BOTH, expand=True)
        self.aui.start()

        self.update_data()

    def update_data(self):
        data = self.aui.udp_data
        if data:
            entries: dict = data["entries"]
            try:
                sorted_entries = sorted(entries.values(), key=lambda x: x["position"])
                self.tree.delete(*self.tree.get_children())
                for entry in sorted_entries:
                    driver = entry["driver"]
                    self.tree.insert(
                        "",
                        tk.END,
                        values=(
                            entry["position"],
                            entry["car_number"],
                            f"{driver['first_name']} {driver['last_name']}",
                            entry["lap"],
                            entry["gear"],
                            entry["kph"],
                            entry["delta"] / 1000.0,
                            f"{entry['current_lap'] / 1000.0:0.3f}",
                            f"{entry['last_lap'] / 1000.0:0.3f}",
                            f"{entry['best_session_lap'] / 1000.0:0.3f}",
                        ),
                    )
            except KeyError:
                print(f"KeyError: {data}")
        self.root.after(100, self.update_data)


if __name__ == "__main__":
    root = tk.Tk()
    aui_info = {
        "name": "Amos Movo",
        "password": "asd",
        "speed": 166,
        "cmd_password": "",
    }
    aui = accUpdInterface("127.0.0.1", 9000, aui_info)
    gui = GuiInterface(root, aui)
    root.mainloop()
