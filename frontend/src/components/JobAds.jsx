import React, { useEffect, useState } from "react";

export default function JobAds(){
  const [items,setItems]=useState([]);
  const [title,setTitle]=useState("");
  const [desc,setDesc]=useState("");
  
  const load=async()=>{
    try {
      const r=await fetch("/api/jobads",{cache:"no-store"});
      const j=await r.json();
      setItems(j.items||[]);
    } catch(e) {
      console.error(e);
    }
  };
  
  const add=async()=>{
    if(!title.trim()) return;
    try {
      await fetch("/api/jobads",{
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({title,description:desc})
      });
      setTitle("");
      setDesc("");
      load();
    } catch(e) {
      console.error(e);
    }
  };
  
  const del=async(id)=>{
    try {
      await fetch(`/api/jobads/${id}`,{method:"DELETE"});
      load();
    } catch(e) {
      console.error(e);
    }
  };
  
  useEffect(()=>{ load(); },[]);
  
  return (
    <div className="space-y-3">
      <div className="flex gap-2">
        <input 
          className="border rounded px-2 py-1 text-sm flex-1" 
          placeholder="Tytuł" 
          value={title} 
          onChange={e=>setTitle(e.target.value)} 
        />
        <input 
          className="border rounded px-2 py-1 text-sm flex-1" 
          placeholder="Opis" 
          value={desc} 
          onChange={e=>setDesc(e.target.value)} 
        />
        <button onClick={add} className="px-3 py-1 border rounded text-sm bg-blue-500 text-white hover:bg-blue-600">Dodaj</button>
      </div>
      <ul className="divide-y border rounded">
        {items.length===0 ? (
          <li className="text-sm opacity-60 py-2 px-3">Brak ogłoszeń</li>
        ) : items.map(i=>(
          <li key={i.id} className="py-2 px-3 flex items-center justify-between hover:bg-gray-50">
            <div>
              <div className="font-medium">{i.title}</div>
              <div className="text-xs opacity-70">{i.description}</div>
            </div>
            <button onClick={()=>del(i.id)} className="text-xs underline text-red-600 hover:text-red-800">Usuń</button>
          </li>
        ))}
      </ul>
    </div>
  );
}