export async function POST(request: Request) {
  try {
    const token = process.env.PEAKGUARD_BACKEND_TOKEN;
    const response = await fetch(
      `${process.env.PEAKGUARD_API_URL || "http://127.0.0.1:8000"}/pareto`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: await request.text(),
        cache: "no-store",
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
