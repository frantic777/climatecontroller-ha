# Kotlin Climate Brain

This Home Assistant app runs the AC Brain v5 controller for a zoned Daikin SkyFi system. It uses
MariaDB for durable operator intent, MQTT room measurements, and a strict confirmed SkyFi command
path.

Updates are distributed as signed, pre-built `amd64` and `aarch64` images. Home Assistant pulls the
image whose tag exactly matches the `version` in `config.yaml`; it does not compile the controller
on the Home Assistant appliance.

Before first start, configure the database, MQTT, controller address, and zones. AUTO actuation and
the physical-write gate are deliberately blocked by default. Existing installations retain their
saved options during routine version updates.

The Home Assistant custom integration is published as `kotlin_ac.zip` alongside each GitHub
release. Controller and integration release artifacts include a SHA-256 checksum manifest.
