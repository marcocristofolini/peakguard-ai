export async function GET() {
  try { const r = await fetch(`${process.env.PEAKGUARD_API_URL || 'http://127.0.0.1:8000'}/scenarios`, {cache:'no-store'}); return new Response(await r.text(), {status:r.status,headers:{'Content-Type':'application/json'}}); }
  catch { return Response.json({detail:'API indisponível. Verifique se o serviço FastAPI está em execução.'},{status:503}); }
}
