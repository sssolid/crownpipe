# CrownPipe

Crown Automotive media processing and data import pipeline.

## Project Structure

```
crownpipe/
├── common/          # Shared utilities (db, logger, paths, config)
├── data/            # Data import modules (FileMaker)
├── media/           # Media processing pipeline
│   ├── systemd/     # Service files
│   └── templates/   # Dashboard templates
└── sync/            # Future sync modules

bin/                 # Entry point scripts
```

## License

Proprietary - Crown Automotive Sales Co., Inc.