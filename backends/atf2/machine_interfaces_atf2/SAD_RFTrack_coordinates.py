"""SAD COORD as an exact change of reference plane, including arrival time.

Rotation/translation conventions follow SAD tcoord.f (1990s implementation)
and the official COORD definition. Native coordinates are mm, mrad, mm/c,
MeV/c. This changes coordinates, never Twiss parameters or beam centroids.
"""
import numpy as np
import RF_Track as rft


def coord_affine(attributes):
    allowed={'DX','DY','DZ','CHI1','CHI2','CHI3','DIR'}
    if set(attributes)-allowed:
        raise ValueError('Unsupported SAD COORD attributes: '+str(set(attributes)-allowed))
    a={k:float(v) for k,v in attributes.items()}
    if not all(np.isfinite(list(a.values()))):raise ValueError('Nonfinite COORD')
    c1,c2,c3=np.cos([a.get('CHI1',0),a.get('CHI2',0),a.get('CHI3',0)])
    s1,s2,s3=np.sin([a.get('CHI1',0),a.get('CHI2',0),a.get('CHI3',0)])
    # SAD tturn/tturne pass (DIR == 0), not bool(DIR), to tcoord.
    if a.get('DIR',0)==0:
        rotation=np.array([[c1*c3+s1*s2*s3,-c2*s3,s1*c3-c1*s2*s3],
                           [-s1*s2*c3+c1*s3,c2*c3,c1*s2*c3+s1*s3],
                           [-s1*c2,-s2,c1*c2]])
        shift=-rotation@np.array([a.get('DX',0),a.get('DY',0),a.get('DZ',0)])*1000
    else:
        rotation=np.array([[c1*c3+s1*s2*s3,s1*s2*c3-c1*s3,s1*c2],
                           [c2*s3,c2*c3,-s2],
                           [-s1*c3+c1*s2*s3,c1*s2*c3+s1*s3,c1*c2]])
        shift=np.array([a.get('DX',0),-a.get('DY',0),-a.get('DZ',0)])*1000
    return rotation,shift


def transform_plane(phase, rotation, shift, mass_mev=rft.electronmass):
    """Intersect the same trajectory with the new plane; no paraxial limit."""
    ps=np.asarray(phase,float)
    if ps.ndim!=2 or ps.shape[1]!=6 or not np.isfinite(ps).all() or np.any(ps[:,5]<=0):
        raise ValueError('Finite forward (N,6) phase space required')
    if not len(ps):return ps.copy()
    direction=np.column_stack((ps[:,1]*.001,ps[:,3]*.001,np.ones(len(ps))))
    direction/=np.linalg.norm(direction,axis=1)[:,None]
    new_direction=direction@rotation.T
    if np.any(new_direction[:,2]<=1e-9):raise ValueError('COORD crosses a backward/tangent reference plane')
    position=np.column_stack((ps[:,0],ps[:,2],np.zeros(len(ps))))@rotation.T+shift
    path=-position[:,2]/new_direction[:,2]
    position+=path[:,None]*new_direction
    out=ps.copy()
    out[:,0]=position[:,0];out[:,2]=position[:,1]
    out[:,1]=new_direction[:,0]/new_direction[:,2]*1000
    out[:,3]=new_direction[:,1]/new_direction[:,2]*1000
    beta=ps[:,5]/np.hypot(ps[:,5],mass_mev)
    out[:,4]+=path/beta
    return out


class SADCoord(rft.UserElement):
    def __init__(self, name, attributes):
        super().__init__(0.)
        self.set_name(name)
        self.rotation,self.shift=coord_affine(attributes)

    def track(self, bunch):
        if bunch.size():
            bunch.set_phase_space(transform_plane(bunch.get_phase_space(),self.rotation,self.shift))

    def btrack(self, bunch):
        if bunch.size():
            bunch.set_phase_space(transform_plane(bunch.get_phase_space(),self.rotation.T,
                                                 -self.rotation.T@self.shift))


def install_sad_coordinates(lattice, records):
    """Replace named zero-length placeholders, retaining director lifetimes."""
    keep=[]
    for record in records:
        if record['sad_type']!='COORD':continue
        name=record['name'];attrs=record.get('source_attributes',record.get('attributes'))
        found=lattice.get_elements_by_name(name)
        found=found if isinstance(found,list) else [found]
        if len(found)!=1 or found[0] is None:raise ValueError('Ambiguous COORD occurrence: '+name)
        if found[0].get_length()!=0:raise ValueError('Nonzero COORD placeholder length')
        element=SADCoord(name,attrs);found[0].replace_with(element);keep.append(element)
    lattice._sad_coord_keepalive=keep
    return [e.get_name() for e in keep]


class RigidHandoff:
    """Fixed frame alignment; preserves 6D geometry, never matches covariance.

    Source/target references must be declared nominal model/survey data, not
    the current bunch or a per-seed optimum. Roll is zero by convention.
    """
    def __init__(self, source, target, target_location='IIN.1'):
        source=np.asarray(source,float);target=np.asarray(target,float)
        def direction(z):
            v=np.array([z[1]*.001,z[3]*.001,1.]);return v/np.linalg.norm(v)
        u,v=direction(source),direction(target)
        cross=np.cross(u,v);dot=float(u@v)
        if dot<-1+1e-10:raise ValueError('Antiparallel injection frames')
        k=np.array([[0.,-cross[2],cross[1]],[cross[2],0.,-cross[0]],[-cross[1],cross[0],0.]])
        self.rotation=np.eye(3)+k+k@k/(1+dot)
        self.shift=np.array([target[0],target[2],0.])-self.rotation@np.array([source[0],source[2],0.])
        self.target_location=target_location
        self.source=source.copy();self.target=target.copy()

    def apply_phase_space(self, phase):
        return transform_plane(phase,self.rotation,self.shift)

    def as_dict(self):
        return dict(kind='fixed rigid reference-plane alignment; no Twiss or dispersion matching',
                    target_location=self.target_location,source_nominal_mm_mrad=self.source.tolist(),
                    target_nominal_mm_mrad=self.target.tolist(),rotation=self.rotation.tolist(),
                    shift_mm=self.shift.tolist(),qualification='historical SAD boundary hypothesis; not surveyed current machine')
