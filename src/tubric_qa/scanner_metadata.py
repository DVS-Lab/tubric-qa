"""Read the scanner allowlist without materializing all JSON values in SQLite."""

from collections import defaultdict
from pathlib import Path

from .io import read_json


class MetadataAmbiguityError(ValueError):
    pass


class ScannerMetadata:
    def __init__(self, root, paths, parse, keys, entity_keys):
        self.root = Path(root)
        self.parse = parse
        self.keys = keys
        self.cache_keys = set(keys) | set(entity_keys)
        self.sidecars = defaultdict(list)
        self.cache = {}
        for path in sorted(paths):
            parsed = parse(path)
            suffix = parsed.pop("suffix", None)
            parsed.pop("extension", None)
            if suffix in ("bold", "T1w", "T2w"):
                self.sidecars[(path.parent, suffix)].append((path, parsed))

    def read(self, image):
        image = Path(image)
        if self.root not in image.parents:
            raise ValueError("Image outside BIDS root")
        parsed = self.parse(image)
        suffix = parsed.pop("suffix", None)
        parsed.pop("extension", None)
        directories = []
        directory = image.parent
        while True:
            directories.append(directory)
            if directory == self.root:
                break
            directory = directory.parent
        metadata = {}
        for directory in reversed(directories):
            matches = [
                (path, entities)
                for path, entities in self.sidecars.get((directory, suffix), [])
                if all(key in parsed and parsed[key] == value for key, value in entities.items())
            ]
            # BIDS forbids multiple applicable sidecars at one hierarchy level.
            # Do not let filename sorting choose a software label implicitly.
            if len(matches) > 1:
                raise MetadataAmbiguityError("Ambiguous metadata sidecars at the same directory level")
            if not matches:
                continue
            path, _ = matches[0]
            if path not in self.cache:
                try:
                    self.cache[path] = {
                        key: value for key, value in read_json(path).items() if key in self.cache_keys
                    }
                except (OSError, ValueError) as exc:
                    self.cache[path] = exc
            payload = self.cache[path]
            if isinstance(payload, Exception):
                raise payload
            for key, value in parsed.items():
                if key in payload and payload[key] is not None and str(payload[key]) != str(value):
                    raise ValueError("Sidecar entity conflicts with image identity")
            metadata.update({key: payload[key] for key in self.keys if key in payload})
        return metadata
