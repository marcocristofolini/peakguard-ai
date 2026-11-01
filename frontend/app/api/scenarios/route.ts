export async function GET() {
  try {
    const token = process.env.PEAKGUARD_BACKEND_TOKEN;
    const response = await fetch(
      `${process.env.PEAKGUARD_API_URL || "http://127.0.0.1:8000"}/scenarios`,
      {
        cache: "no-store",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      },
    );
    return new Response(await response.text(), {
      status: response.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return Response.json(
      {
        detail:
          "API indisponível. Verifique se o serviço FastAPI está em execução.",
      },
      { status: 503 },
    );
  }
}
