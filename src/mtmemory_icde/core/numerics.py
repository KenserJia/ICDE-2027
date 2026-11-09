"""Outward-evaluated range-mean certificate; target values are finite float32.

Supported estimator kernels use binary64 sums, division, multiplication and
addition. Every cell's sum reduction has depth at most max_cell_width-1.
See the independent review7 derivation for the componentwise gamma bound.
"""
import numpy as np

class MissingHistory(ValueError):
    pass

def up(x):
    return np.nextafter(x, np.inf)

def gamma_upper(n, unit_roundoff=2.0**-53):
    n=int(n)
    if not 0<n<2**32 or n*unit_roundoff>=1:
        raise ValueError('unsupported arithmetic depth')
    nu=up(float(n)*unit_roundoff)
    den=np.nextafter(1.-nu,-np.inf)
    if den<=0:raise ValueError('gamma denominator')
    return float(up(nu/den))

def certified_mean(cells,lo,hi,channels,max_cell_width):
    """Consume disjoint populated cells (start,count,sum,min,max), in order."""
    if not 0<hi-lo<=2**20 or not 0<max_cell_width<=2**20:
        raise ValueError('supported length domain')
    total=np.zeros(channels);raw=np.zeros(channels);upper=np.zeros(channels)
    mag=np.zeros(channels);covered=terms=0;partial=False
    for left,m,s,mn,mx in cells:
        m=int(m);r=max(0,min(hi,left+m)-max(lo,left))
        if not r:continue
        if m<=0 or m>max_cell_width:raise ValueError('populated cell length')
        total+=(r/m)*s;covered+=r;terms+=1
        mag=up(mag+up(r*np.maximum(np.abs(mn),np.abs(mx))))
        if r!=m:
            partial=True;coef=r*(m-r)
            raw+=(coef/m)*(mx-mn)
            # Positive outward evaluation of the exact extremal expression.
            upper=up(upper+up(up(coef/float(m))*up(mx-mn)))
    if covered!=hi-lo:raise MissingHistory('incomplete history interval')
    width=hi-lo;value=total/width;analytical=raw/width
    Bup=up(upper/width);Gup=up(mag/width)
    n=max_cell_width+terms+4;g=gamma_upper(n)
    numerical=up(g*Gup)
    analytical_evaluation=up(np.maximum(0.,Bup-analytical))
    rounding=up(numerical+analytical_evaluation)
    total_bound=up(analytical+rounding)
    if not all(np.all(np.isfinite(x)) for x in [value,analytical,total_bound]):
        raise FloatingPointError('nonfinite estimator or certificate')
    return dict(status='ANSWERED',value=value,resolution='APPROX' if partial else 'EXACT',
                bound=analytical,analytical_upper=Bup,rounding_bound=rounding,
                total_bound=total_bound,contributing_cells=terms,arithmetic_depth=n)
