# installer for the rmi driver
# Copyright 2025 Bram Oosterlynck

from weecfg.extension import ExtensionInstaller


def loader():
    return RMIInstaller()


class RMIInstaller(ExtensionInstaller):
    def __init__(self):
        super(RMIInstaller, self).__init__(
            version="0.2",
            name="rmi",
            description="A driver or service which fetches data from RMI (Belgium)",
            author="Bram Oosterlynck",
            author_email="bram.oosterlynck@gmail.com",
            config={
                "Station": {"station_type": "RMI"},
                "RMI": {"poll_interval": "60", "driver": "user.rmi"},
            },
            files=[("bin/user", ["bin/user/rmi.py"])],
        )
