import { useEffect, useRef } from "react";
import type { EditorSettings } from "./Editor";

type Overlay = EditorSettings["overlay"];
const fract=(value:number)=>value-Math.floor(value);
const random=(seed:number)=>fract(Math.sin(seed*91.731+17.17)*43758.5453);
const smoothstep=(a:number,b:number,value:number)=>{const x=Math.max(0,Math.min(1,(value-a)/(b-a)));return x*x*(3-2*x)};

function softLight(ctx:CanvasRenderingContext2D,x:number,y:number,radius:number,color:string,alpha:number){
  const gradient=ctx.createRadialGradient(x,y,0,x,y,radius);
  gradient.addColorStop(0,color.replace("ALPHA",String(alpha)));
  gradient.addColorStop(.28,color.replace("ALPHA",String(alpha*.7)));
  gradient.addColorStop(1,color.replace("ALPHA","0"));
  ctx.fillStyle=gradient;ctx.fillRect(x-radius,y-radius,radius*2,radius*2);
}

export default function OverlayCanvas({type,intensity,time,beatPulse}:{type:Overlay;intensity:number;time:number;beatPulse:number}){
  const canvasRef=useRef<HTMLCanvasElement>(null);
  const grainRef=useRef<{canvas:HTMLCanvasElement;ctx:CanvasRenderingContext2D;image:ImageData}|null>(null);
  useEffect(()=>{
    const canvas=canvasRef.current,parent=canvas?.parentElement;if(!canvas||!parent)return;
    const draw=()=>{
      const bounds=parent.getBoundingClientRect(),dpr=Math.min(1.5,window.devicePixelRatio||1);
      const width=Math.max(1,Math.round(bounds.width*dpr)),height=Math.max(1,Math.round(bounds.height*dpr));
      if(canvas.width!==width||canvas.height!==height){canvas.width=width;canvas.height=height}
      const ctx=canvas.getContext("2d");if(!ctx)return;ctx.clearRect(0,0,width,height);
      const strength=Math.pow(Math.max(0,intensity)/100,1.28);if(type==="none"||strength<=0)return;

      if(type==="vignette"){
        const gradient=ctx.createRadialGradient(width*.5,height*.47,Math.min(width,height)*.18,width*.5,height*.5,Math.max(width,height)*.72);
        gradient.addColorStop(0,"rgba(0,0,0,0)");gradient.addColorStop(.62,"rgba(0,0,0,0)");gradient.addColorStop(1,`rgba(0,0,0,${.72*strength})`);ctx.fillStyle=gradient;ctx.fillRect(0,0,width,height);return;
      }
      if(type==="grain"){
        const sampleWidth=Math.min(220,Math.max(72,Math.ceil(width/4))),sampleHeight=Math.min(160,Math.max(48,Math.ceil(height/4)));
        let grain=grainRef.current;
        if(!grain||grain.canvas.width!==sampleWidth||grain.canvas.height!==sampleHeight){const buffer=document.createElement("canvas");buffer.width=sampleWidth;buffer.height=sampleHeight;const bufferCtx=buffer.getContext("2d",{alpha:true});if(!bufferCtx)return;grain={canvas:buffer,ctx:bufferCtx,image:bufferCtx.createImageData(sampleWidth,sampleHeight)};grainRef.current=grain}
        let seed=(Math.floor(time*8)+1)*2654435761;const pixels=grain.image.data;
        for(let index=0;index<pixels.length;index+=4){seed=(seed*1664525+1013904223)>>>0;const value=58+(seed>>>24);pixels[index]=value;pixels[index+1]=value;pixels[index+2]=value;pixels[index+3]=255}
        grain.ctx.putImageData(grain.image,0,0);ctx.save();ctx.globalCompositeOperation="soft-light";ctx.globalAlpha=.16*strength;ctx.imageSmoothingEnabled=false;ctx.drawImage(grain.canvas,0,0,width,height);ctx.restore();return;
      }
      if(type==="dust"||type==="scratches"){
        ctx.globalCompositeOperation="screen";const count=type==="dust"?32:18;
        for(let i=0;i<count;i++){const life=3.8+random(i+4)*7.2,phase=fract(time/life+random(i+80)),envelope=Math.sin(Math.PI*phase)**4;if(envelope<.025)continue;const x=fract(random(i+1)+time*(.003+random(i+20)*.006))*width,y=fract(random(i+2)-time*(.006+random(i+30)*.012))*height,radius=(.7+random(i+5)*2.8)*dpr;softLight(ctx,x,y,radius*4,"rgba(238,231,210,ALPHA)",envelope*strength*.22)}
        if(type==="scratches")for(let i=0;i<3;i++){const cycle=5.5+random(i+91)*6,phase=fract(time/cycle+random(i+160)),envelope=smoothstep(.02,.09,phase)*(1-smoothstep(.2,.34,phase));if(envelope<=.01)continue;const x=(.08+random(Math.floor(time/cycle)*11+i)*.84)*width,lean=(random(i+9)-.5)*4*dpr;ctx.strokeStyle=`rgba(245,241,224,${envelope*strength*.24})`;ctx.lineWidth=Math.max(.55*dpr,1);ctx.beginPath();ctx.moveTo(x,height*.03);ctx.quadraticCurveTo(x+lean,height*.52,x-lean*.4,height*.96);ctx.stroke()}return;
      }
      if(type==="light_leaks"){
        ctx.globalCompositeOperation="screen";const drift=Math.sin(time*.21),bloom=1+beatPulse*.12;
        softLight(ctx,width*(-.13+drift*.035),height*(.35+Math.sin(time*.13)*.09),Math.max(width,height)*.72,"rgba(255,72,24,ALPHA)",strength*.23*bloom);
        softLight(ctx,width*(1.12-drift*.025),height*(.7+Math.cos(time*.17)*.08),Math.max(width,height)*.68,"rgba(255,40,112,ALPHA)",strength*.14*bloom);return;
      }
      if(type==="film_burn"){
        const phase=fract(time/9.7+.11),event=smoothstep(.02,.08,phase)*(1-smoothstep(.19,.34,phase));if(event<.01)return;
        ctx.globalCompositeOperation="screen";const side=random(Math.floor(time/9.7))>.5?1:0,x=side?width*1.06:-width*.06;
        softLight(ctx,x,height*(.36+random(Math.floor(time/9.7)+3)*.3),Math.max(width,height)*(.56+event*.18),"rgba(255,45,4,ALPHA)",strength*(.04+event*.5));softLight(ctx,x+(side?-1:1)*width*.08,height*.55,Math.max(width,height)*.32,"rgba(255,190,38,ALPHA)",strength*event*.38);return;
      }
      if(type==="rain"){
        ctx.globalCompositeOperation="screen";ctx.lineCap="round";
        for(let layer=0;layer<2;layer++)for(let i=0;i<(layer?34:22);i++){const speed=layer?1.15:.62,length=layer?height*.052:height*.027,travel=fract(random(i+layer*100)+time*speed*.24),x=fract(random(i+41+layer*60)+travel*.16)*width,y=(travel*1.3-.16)*height;ctx.strokeStyle=`rgba(195,222,234,${strength*(layer?.17:.08)})`;ctx.lineWidth=(layer?1.05:.65)*dpr;ctx.beginPath();ctx.moveTo(x,y);ctx.lineTo(x+length*.24,y+length);ctx.stroke()}return;
      }
      if(type==="scanlines"){
        const spacing=Math.max(4,Math.round(4*dpr));ctx.fillStyle=`rgba(0,0,0,${strength*.19})`;for(let y=0;y<height;y+=spacing)ctx.fillRect(0,y,width,Math.max(1,dpr*.55));const roll=fract(time*.075)*height,gradient=ctx.createLinearGradient(0,roll-height*.18,0,roll+height*.18);gradient.addColorStop(0,"rgba(255,255,255,0)");gradient.addColorStop(.5,`rgba(210,225,255,${strength*.035})`);gradient.addColorStop(1,"rgba(255,255,255,0)");ctx.fillStyle=gradient;ctx.fillRect(0,0,width,height);return;
      }
      if(type==="vhs"){
        ctx.save();ctx.globalCompositeOperation="screen";
        const jitter=Math.round(Math.sin(time*37)*1.2*dpr),lineSpacing=Math.max(4,Math.round(5*dpr));
        ctx.fillStyle=`rgba(170,205,255,${strength*.045})`;for(let y=(Math.floor(time*18)%lineSpacing);y<height;y+=lineSpacing)ctx.fillRect(jitter,y,width,Math.max(1,.55*dpr));
        const cycle=fract(time*.21),trackY=cycle*height,bandHeight=Math.max(3,height*.025);const band=ctx.createLinearGradient(0,trackY-bandHeight,0,trackY+bandHeight);band.addColorStop(0,"rgba(255,255,255,0)");band.addColorStop(.5,`rgba(225,238,255,${strength*.13})`);band.addColorStop(1,"rgba(255,255,255,0)");ctx.fillStyle=band;ctx.fillRect(0,trackY-bandHeight,width,bandHeight*2);
        const event=fract(time/3.7),tear=smoothstep(.01,.05,event)*(1-smoothstep(.11,.2,event));if(tear>.01){const tearY=(.16+random(Math.floor(time/3.7)+9)*.68)*height;ctx.fillStyle=`rgba(220,240,255,${tear*strength*.2})`;ctx.fillRect((random(Math.floor(time*9))-.5)*width*.05,tearY,width,Math.max(1,2*dpr));for(let i=0;i<5;i++){const y=tearY+(i+1)*3*dpr,x=random(i+Math.floor(time*13))*width*.7;ctx.fillRect(x,y,width*(.04+random(i+20)*.18),Math.max(1,.7*dpr))}}
        ctx.fillStyle=`rgba(255,45,105,${strength*.025})`;ctx.fillRect(0,0,Math.max(1,2*dpr),height);ctx.fillStyle=`rgba(40,205,255,${strength*.03})`;ctx.fillRect(width-Math.max(1,2*dpr),0,Math.max(1,2*dpr),height);ctx.restore();return;
      }
      if(type==="bokeh"){
        ctx.globalCompositeOperation="screen";const colors=["rgba(255,190,108,ALPHA)","rgba(114,210,255,ALPHA)","rgba(255,112,166,ALPHA)"];
        for(let i=0;i<12;i++){const depth=.35+random(i+8)*.65,x=fract(random(i+1)+time*.0025*depth)*width,y=fract(random(i+2)-time*.0018*depth)*height,radius=Math.min(width,height)*(.025+random(i+5)*.075);softLight(ctx,x,y,radius*1.8,colors[i%colors.length],strength*(.055+.06*depth))}return;
      }
      if(type==="prism"){
        ctx.globalCompositeOperation="screen";const shift=Math.sin(time*.19)*width*.04,gradient=ctx.createLinearGradient(width*(-.25)+shift,height,width*(.72)+shift,0);gradient.addColorStop(.2,"rgba(255,40,105,0)");gradient.addColorStop(.38,`rgba(255,40,105,${strength*.08})`);gradient.addColorStop(.49,`rgba(255,218,80,${strength*.065})`);gradient.addColorStop(.6,`rgba(65,220,255,${strength*.08})`);gradient.addColorStop(.78,"rgba(65,220,255,0)");ctx.fillStyle=gradient;ctx.fillRect(0,0,width,height);
      }
    };
    draw();const observer=new ResizeObserver(draw);observer.observe(parent);return()=>observer.disconnect();
  },[type,intensity,time,beatPulse]);
  return <canvas ref={canvasRef} className={`live-overlay-canvas overlay-${type}`} aria-hidden="true"/>;
}
