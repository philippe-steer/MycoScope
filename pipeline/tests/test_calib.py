import numpy as np

from mycoscope_pipeline.calib.fastmodel import fruiting_batch, fruiting_one, params_from_species
from mycoscope_pipeline.model import Weather, fruiting, load_species
from tests.make_fixture import weather


def test_fast_equals_reference():
    w = weather()
    for sp in load_species():
        p = params_from_species(sp)
        for elev, dm in ((250.0, 0.0), (900.0, -0.125), (50.0, 0.25)):
            ref = fruiting(sp, w, elev, dm)
            got = fruiting_one(p, w.precip, w.tmean, w.tmin, w.et0, w.doy, w.elevation, elev, dm)
            assert np.allclose(ref, got, atol=1e-9), sp["id"]


def test_batch_shapes():
    w = weather()
    sp = load_species()[0]
    p = params_from_species(sp)
    n = 5
    P = np.tile(w.precip, (n, 1))
    idx = np.tile(np.arange(60, 67), (n, 1))
    F = fruiting_batch(p, P, np.tile(w.tmean, (n, 1)), np.tile(w.tmin, (n, 1)), np.tile(w.et0, (n, 1)),
                       np.tile(w.doy, (n, 1)), np.full(n, w.elevation), np.full(n, 250.0), np.zeros(n), idx)
    assert F.shape == (n, 7)
