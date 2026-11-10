from pathlib import Path
R=Path(__file__).resolve().parents[2]
F=R/'paper/IEEE-conference-template-062824/figures'
O=R/'results/framework_20261109'
F.mkdir(parents=True,exist_ok=True)
O.mkdir(parents=True,exist_ok=True)
s=(R/'repro/framework_20261109/draw.py').read_text()
s=s.replace("ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'paper/IEEE-conference-template-062824/figures/framework_20261109';QA=ROOT/'results/framework_20261109'",f"ROOT=Path({str(R)!r});OUT=Path({str(F/'review7_framework')!r});QA=Path({str(O/'framework_QA')!r});OUT.mkdir(exist_ok=True);QA.mkdir(exist_ok=True)")
s=s.replace('Accounted native service state','Accounted joint service state').replace('纳入资源核算的原生服务状态','纳入资源核算的联合服务状态')
s=s.replace("('Certificate extension','误差证书扩展')","('Certificate state','误差证书状态')").replace('Rounding allowance F\\n\\nSeparate evaluation','Arithmetic allowance F\\n\\nJoint checkpoint').replace('数值误差余量 F\\n\\n单独评估','数值误差余量 F\\n\\n联合检查点')
s=s.replace('Solid: native service paths. Dashed: separately evaluated certificate augmentation.','Solid: service execution. Dashed: certificate-to-cell associations in joint state.').replace('实线：原生服务路径。虚线：单独评估的误差证书扩展。','实线：服务执行路径。虚线：联合状态中的证书与单元关联。')
s=s.replace('Value / status\\nPrefix / source\\nResolution','Value / status / T\\nPrefix / source\\nResolution')
s=s.replace("for lang in ['en','zh']:draw(lang)","for lang in ['en']:draw(lang)")
(O/'framework_draw.py').write_text(s)
exec(compile(s,str(O/'framework_draw.py'),'exec'),{'__file__':str(O/'framework_draw.py')})
