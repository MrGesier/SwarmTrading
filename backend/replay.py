"""Rebuild derived states from raw recorder events using the live Engine.

Supports Parquet when pyarrow is installed and JSONL fallback recordings when it
is not. Usage: python replay.py ../data/<recording-id> --output replayed.jsonl
"""
import argparse
import json
from pathlib import Path
from typing import Iterable

try:
    import pyarrow.parquet as pq
except ImportError:
    pq = None

from engine import Engine, OrderBook, SequenceGap


def _rows(directory: Path) -> Iterable[dict]:
    parquet = sorted(directory.glob('*.parquet'))
    jsonl = sorted(directory.glob('*.jsonl'))
    if parquet and pq is None:
        raise RuntimeError('This recording is Parquet; install pyarrow to replay it.')
    for file in parquet:
        assert pq is not None
        for batch in pq.ParquetFile(file).iter_batches():
            yield from batch.to_pylist()
    for file in jsonl:
        with file.open('r', encoding='utf-8') as handle:
            for line in handle:
                line = line.strip()
                if line:
                    yield json.loads(line)


def replay_events(directory):
    directory = Path(directory)
    book, engine = OrderBook(), Engine()
    mode, symbol = directory.name.split('-')[:2]
    last_depth = 0
    for row in _rows(directory):
        ts, event = row['received'], json.loads(row['payload'])
        kind = event['type']
        if kind == 'reset':
            book, engine = OrderBook(), Engine()
            last_depth = 0
        elif kind == 'snapshot':
            book.snapshot(event['data'])
            last_depth = ts
        elif kind == 'depth':
            try:
                if book.update(event['data']):
                    last_depth = ts
            except SequenceGap:
                book.valid = False
        elif kind == 'trade':
            d = event['data']
            engine.trade(ts, float(d['p']), float(d['q']), d['m'])
        elif kind == 'clock':
            book.valid = event['valid']
            health = dict(
                status='HEALTHY' if book.valid and ts-last_depth < 3 and event['health'] == 'HEALTHY' else 'STALE',
                age_ms=round((ts-last_depth)*1000), sequence=book.sequence, message='', recording=directory.name,
            )
            state = engine.calculate(book, ts, mode, symbol, health)
            if state:
                yield state


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('directory', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error('Recording directory does not exist')
    count = 0
    with args.output.open('w', encoding='utf-8') as output:
        for state in replay_events(args.directory):
            output.write(json.dumps(state) + '\n')
            count += 1
    print(f'Replayed {count} states to {args.output}')
