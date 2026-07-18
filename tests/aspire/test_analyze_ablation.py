from scripts.analyze_ablation import mann_whitney_u

def test_u_of_clearly_separated_samples():
    # b strictly greater than a: U for a should be 0 (no a beats any b)
    U, z = mann_whitney_u([0.0, 0.1, 0.2], [0.8, 0.9, 1.0])
    assert U == 0.0
    assert z < 0            # a ranks below b

def test_u_symmetry_and_midranks():
    # identical samples: U = n*m/2, z = 0
    U, z = mann_whitney_u([0.5, 0.5], [0.5, 0.5])
    assert U == 2.0         # n*m/2 = 2*2/2
    assert abs(z) < 1e-9
