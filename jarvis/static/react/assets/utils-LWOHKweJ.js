function i(s){const n=new URLSearchParams;Object.entries(s).forEach(([e,t])=>{t!=null&&t!==""&&n.set(e,String(t))});const r=n.toString();return r?`?${r}`:""}export{i as b};
