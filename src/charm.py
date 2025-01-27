#!/usr/bin/env python3

# Copyright 2024 Clément Gassmann-Prince
# See LICENSE file for licensing details.

"""
    Charm for deploying and managing Ollama.
    For more information about Ollama:
        Homepage: https://ollama.com/
        Github: https://github.com/ollama/ollama
"""

import logging
import subprocess
import textwrap

from ops import InstallEvent, StartEvent, ConfigChangedEvent
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, MaintenanceStatus, BlockedStatus

logger = logging.getLogger(__name__)

def run_shell(cmd: str):
    """ Shorthand to run a shell command """
    subprocess.run(cmd.split(), check=True)

class OllamaCharm(CharmBase):
    """ Machine charm for Ollama """

    _charm_state = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

        self._charm_state.set_default(installed=False, port=self.config["port"])

    def _on_install(self, _: InstallEvent):
        """ Install Ollama service """
        self.unit.status = MaintenanceStatus("Installing Ollama")

        try:
            self._install_ollama()
            self._setup_ollama_service(self._charm_state.port)

            self._charm_state.installed = True
            self.unit.status = MaintenanceStatus("Ollama installed")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to install Ollama: {e}")
            self.unit.status = BlockedStatus("Failed to install Ollama")

    def _on_start(self, _: StartEvent):
        """ Start Ollama service """
        if not self._charm_state.installed:
            self.unit.status = BlockedStatus("Cannot start, Ollama is not installed")
            return

        self.unit.status = MaintenanceStatus("Starting Ollama service")
        try:
            run_shell(f"sudo systemctl start ollama.service")

            self.unit.open_port("tcp", self._charm_state.port)
            self.unit.status = ActiveStatus("Ollama is running")
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to start Ollama service: {e}")
            self.unit.status = BlockedStatus("Failed to start Ollama service")

    def _on_config_changed(self, _: ConfigChangedEvent):
        """ Apply configuration changes """
        new_port = self.config["port"]
        port_has_changed = new_port != self._charm_state.port

        if port_has_changed:
            self.unit.status = MaintenanceStatus("Updating Ollama port")
            try:
                self.unit.close_port("tcp", self._charm_state.port)

                self._setup_ollama_service(new_port)
                run_shell(f"sudo systemctl restart ollama.service")

                self.unit.open_port("tcp", new_port)
                self._charm_state.port = new_port
                self.unit.status = ActiveStatus("Ollama port updated")

            except subprocess.CalledProcessError as e:
                logger.error(f"Failed to update Ollama port: {e}")
                self.unit.status = BlockedStatus("Failed to update Ollama port")

    def _install_ollama(self):
        """ Download and install Ollama """
        run_shell("sudo curl -L https://ollama.com/download/ollama-linux-amd64 -o /usr/bin/ollama")
        run_shell("sudo chmod +x /usr/bin/ollama")
        run_shell("sudo useradd -r -s /bin/false -m -d /usr/share/ollama ollama")

    def _setup_ollama_service(self, port: int):
        """ Sets up Ollama systemd service. """
        service_content = textwrap.dedent(f"""
            [Unit]
            Description=Ollama Service
            After=network-online.target

            [Service]
            Environment="OLLAMA_HOST=0.0.0.0:{str(port)}"
            ExecStart=/usr/bin/ollama serve
            User=ollama
            Group=ollama
            Restart=always
            RestartSec=3

            [Install]
            WantedBy=default.target
        """)
        with open("/etc/systemd/system/ollama.service", "w") as f:
            f.write(service_content)

        run_shell("sudo systemctl daemon-reload")

if __name__ == "__main__":
    main(OllamaCharm)
