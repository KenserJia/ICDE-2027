"""Same retained statistics, estimator, and sum-depth assumptions as numerics.py."""
import numpy as np
from .numerics import MissingHistory, gamma_upper, up

def down(x):
    return np.nextafter(x, -np.inf)

def cell_bounds(s, mn, mx, m, r, sum_gamma):
    """Return ordinary/outward span and sum-aware numerator-error bounds.

    m and r may be scalar integers or broadcastable arrays. Stored s is binary64.
    The exact sum lies in s +/- gamma_b*m*max(abs(mn),abs(mx)). Every subsequent
    signed interval operation is rounded outward. No additional state is retained.
    """
    coef = r * (m-r)
    span = (coef/m) * (mx-mn)
    span_up = up(up(coef/m) * up(mx-mn))
    delta = up(up(sum_gamma*m) * np.maximum(np.abs(mn), np.abs(mx)))
    slo, shi = down(s-delta), up(s+delta)
    alo = np.maximum(down(r*mn), down(slo-up((m-r)*mx)))
    ahi = np.minimum(up(r*mx), up(shi-down((m-r)*mn)))
    edelta = up(up(r*delta)/m)
    elo = down(down(down(r*s)/m)-edelta)
    ehi = up(up(up(r*s)/m)+edelta)
    tighter_up = np.minimum(span_up, np.maximum(0., np.maximum(up(ehi-alo), up(ahi-elo))))
    nominal_lo = np.maximum(r*mn, s-(m-r)*mx)
    nominal_hi = np.minimum(r*mx, s-(m-r)*mn)
    nominal_estimate = (r/m)*s
    tighter = np.minimum(span, np.maximum(0., np.maximum(nominal_estimate-nominal_lo, nominal_hi-nominal_estimate)))
    return span, span_up, tighter, tighter_up

def sum_aware_mean(cells, lo, hi, channels, max_cell_width):
    """Consume the same disjoint populated cells and preserve estimator order."""
    width=hi-lo
    if not 0<width<=2**20 or not 0<max_cell_width<=2**20:
        raise ValueError('supported length domain')
    total=np.zeros(channels);old_raw=total.copy();old_upper=total.copy()
    raw=total.copy();upper=total.copy();mag=total.copy()
    covered=terms=0;partial=False;sum_gamma=gamma_upper(max_cell_width)
    for left,m,s,mn,mx in cells:
        m=int(m);r=max(0,min(hi,left+m)-max(lo,left))
        if not r:continue
        if not 0<m<=max_cell_width:raise ValueError('populated cell length')
        total+=(r/m)*s;covered+=r;terms+=1
        mag=up(mag+up(r*np.maximum(np.abs(mn),np.abs(mx))))
        if r!=m:
            partial=True
            a,au,z,zu=cell_bounds(s,mn,mx,m,r,sum_gamma)
            old_raw+=a;old_upper=up(old_upper+au)
            raw+=z;upper=up(upper+zu)
    if covered!=width:raise MissingHistory('incomplete history interval')
    value=total/width;g=gamma_upper(max_cell_width+terms+4)
    numerical=up(g*up(mag/width))
    def finish(a,u):
        analytical=a/width;Bup=up(u/width)
        rounding=up(numerical+up(np.maximum(0.,Bup-analytical)))
        return analytical,Bup,rounding,up(analytical+rounding)
    original=finish(old_raw,old_upper);tight=finish(raw,upper)
    # Both certificates are valid. Select componentwise to ensure non-increase
    # even when the last rounded additions differ by a few ulps.
    use=tight[3]<=original[3]
    analytical,Bup,rounding,bound=[np.where(use,a,b) for a,b in zip(tight,original)]
    if not all(np.all(np.isfinite(x)) for x in [value,analytical,bound]):
        raise FloatingPointError('nonfinite estimator or certificate')
    return dict(status='ANSWERED',value=value,resolution='APPROX' if partial else 'EXACT',
                bound=analytical,analytical_upper=Bup,rounding_bound=rounding,
                total_bound=bound,contributing_cells=terms,
                arithmetic_depth=max_cell_width+terms+4)
