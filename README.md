# WeeWX RMI

A driver or service which fetches data from the [RMI](https://www.meteo.be/en/about-rmi/strategy).

## Installation

This driver requires the [irm-kmi-api library](https://github.com/jdejaegh/irm-kmi-api).
Version 1.0 or higher is required. This Python package can be installed via Pip:

```shell
pip install irm-kmi-api
```

Then you can install this extension:

```shell
weectl extension install https://github.com/boosterl/weewx-rmi/archive/refs/heads/main.zip
```

### Configuring as a driver

```shell
weectl station reconfigure --driver=user.rmi --no-prompt
```

### Configuring as a service

Edit weewx.conf and under the [Engine] [[Services]] stanza add an entry
user.rmi.RMIService to the data_services option. It should look something
like:

```
[Engine]

    [[Services]]
        ....
        data_services = user.rmi.RMIService
```

Under the [RMI] stanza, define the type of packets to bind to, and enable the
service:

```
[RMI]
    service = true
    binding = loop
```

Lastly, restart the weewx service for both configuration methods:

```shell
sudo systemctl restart weewx
```
