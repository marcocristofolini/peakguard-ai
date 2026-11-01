export async function POST(request: Request) {
  try {
    const response = await fetch(
      `${process.env.PEAKGUARD_API_URL || "http://127.0.0.1:8000"}/explanations`,
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
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
          "Validação indisponível. Verifique se a API FastAPI está em execução.",
      },
      { status: 503 },
    );
  }
}
