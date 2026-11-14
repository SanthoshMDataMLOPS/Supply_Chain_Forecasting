import os

import pytest

pytest.importorskip("kfp")


def test_pipelines_compile(tmp_path):
    from pipelines.run_pipeline import _compile

    paths = _compile("us-docker.pkg.dev/test/mlops/inbound-forecast:test", str(tmp_path))
    for p in paths.values():
        assert os.path.getsize(p) > 1000
