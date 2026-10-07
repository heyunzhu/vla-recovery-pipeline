"""Triangle-surface distance and two-ray parity diagnostics; no admission gate."""
import numpy as np


def mesh_closed_edge_check(triangles):
    t=np.asarray(triangles,float)
    vertices,indices=np.unique(t.reshape(-1,3),axis=0,return_inverse=True)
    faces=indices.reshape(-1,3)
    edges=np.sort(np.concatenate((faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]])),axis=1)
    _,counts=np.unique(edges,axis=0,return_counts=True)
    degenerate=int((np.linalg.norm(np.cross(t[:,1]-t[:,0],t[:,2]-t[:,0]),axis=1)<=1e-12).sum())
    return dict(edge_count=len(counts),nonmanifold_or_open_edge_count=int((counts!=2).sum()),
                degenerate_triangle_count=degenerate,closed_edge_topology=bool(np.all(counts==2) and not degenerate))


def point_surface_distance(point,triangles):
    t=np.asarray(triangles,float);p=np.asarray(point,float)
    a,b,c=t[:,0],t[:,1],t[:,2];ab=b-a;ac=c-a;ap=p-a
    normal=np.cross(ab,ac);nn=np.sum(normal*normal,axis=1)
    signed=np.sum(ap*normal,axis=1)
    projected=ap-normal*np.divide(signed,nn,out=np.zeros_like(signed),where=nn>1e-24)[:,None]
    d00=np.sum(ab*ab,axis=1);d01=np.sum(ab*ac,axis=1);d11=np.sum(ac*ac,axis=1)
    d20=np.sum(projected*ab,axis=1);d21=np.sum(projected*ac,axis=1);den=d00*d11-d01*d01
    u=np.divide(d11*d20-d01*d21,den,out=np.zeros_like(den),where=den>1e-24)
    v=np.divide(d00*d21-d01*d20,den,out=np.zeros_like(den),where=den>1e-24)
    inside=(den>1e-24)&(u>=0)&(v>=0)&(u+v<=1)
    distance=np.full(len(t),np.inf)
    distance[inside]=np.abs(signed[inside])/np.sqrt(nn[inside])
    for start,end in ((a,b),(b,c),(c,a)):
        edge=end-start;length=np.sum(edge*edge,axis=1)
        fraction=np.clip(np.divide(np.sum((p-start)*edge,axis=1),length,out=np.zeros_like(length),where=length>1e-24),0,1)
        distance=np.minimum(distance,np.linalg.norm(p-(start+fraction[:,None]*edge),axis=1))
    return float(distance.min())


def ray_parity(point,triangles,direction):
    """Parity with shared-edge ray hits marked ambiguous instead of merged."""
    t=np.asarray(triangles,float);d=np.asarray(direction,float);d=d/np.linalg.norm(d)
    e1=t[:,1]-t[:,0];e2=t[:,2]-t[:,0];h=np.cross(d,e2);det=np.sum(e1*h,axis=1)
    valid=np.abs(det)>1e-12;inv=np.divide(1,det,out=np.zeros_like(det),where=valid)
    s=np.asarray(point,float)-t[:,0];u=np.sum(s*h,axis=1)*inv;q=np.cross(s,e1)
    v=(q @ d)*inv;distance=np.sum(e2*q,axis=1)*inv
    hits=valid&(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)&(distance>1e-9)
    if np.any(hits&((u<1e-8)|(v<1e-8)|(u+v>1-1e-8))):return None
    return bool(int(hits.sum())%2)


def classify_mesh_points(points,triangles,*,margin_m=.002):
    points=np.asarray(points,float);triangles=np.asarray(triangles,float)
    if points.ndim!=2 or points.shape[1]!=3 or triangles.ndim!=3 or triangles.shape[1:]!=(3,3) or not len(triangles):
        raise ValueError('xyz points and triangles required')
    if not np.isfinite(points).all() or not np.isfinite(triangles).all() or not 0<=margin_m<=.01:
        raise ValueError('finite geometry and bounded margin required')
    topology=mesh_closed_edge_check(triangles);rows=[]
    for p in points:
        distance=point_surface_distance(p,triangles)
        parity=[ray_parity(p,triangles,d) for d in ([1,.371,.529],[-.217,1,.613])]
        agreed=topology['closed_edge_topology'] and parity[0] is not None and parity[0]==parity[1]
        category=('near_triangle_surface' if distance<=margin_m else
                  'inside_two_ray_candidate' if agreed and parity[0] else
                  'outside_two_ray_candidate' if agreed else 'unknown')
        rows.append(dict(category=category,surface_distance_m=distance,ray_parity=parity))
    return dict(topology=topology,points=rows,method='unsigned_triangle_distance_and_two_generic_rays',execution_allowed=False)
