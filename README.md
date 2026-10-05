# MF4 Signal Mapper

Standalone Windows Python tool for:

    raw.mf4 + one common CAN DBC + marker-based channel mapping
        -> mapped.mf4

The input raw MF4 is preserved. Decoded DBC signal groups are appended to a new MF4.

## GUI

Run:

```bat
.venv\Scripts\activate
python main.py
```

GUI workflow:

1. Import raw MF4
2. Import one common CAN DBC
3. Review auto-detected CAN channel mapping
4. Choose output MF4
5. Press `Export mapped MF4`

The `Remove` buttons only clear the selected file from the current session; they do not delete files from disk.

## Auto channel mapping

The tool does NOT assume CAN1=PT. It inspects message IDs observed on each physical CAN channel and applies:

- 0x501 -> BD
- 0x51B -> PT
- 0x154 OR 0x529 -> CH
- 0x504 -> INFO
- 0x513 -> BA

If a channel matches zero rules it stays physically named CANx. If it matches more than one rule, it is marked ambiguous and no logical name is inferred.

## CLI

```bat
python main.py --cli ^
  --mf4 "D:\log\raw.mf4" ^
  --dbc "D:\dbc\vehicle.dbc" ^
  --config "mapping.json" ^
  --output "D:\log\mapped.mf4"
```

## Dependencies

- Python 3.10+
- asammdf 8.8.27
- PySide6

`asammdf` provides MDF4 read/write and CAN bus logging + DBC signal extraction; PySide6 provides the Windows GUI.
