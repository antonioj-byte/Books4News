import { timingSafeEqual } from "node:crypto";
import { NextResponse, type NextRequest } from "next/server";

// Contraseña de la web desplegada (FOLIO_CLAVE_WEB): autenticación básica del navegador, cualquier
// usuario. Protege también /api y /diseno, que se reenvían a la API. Sin la variable (en local),
// no se pide nada.
export function proxy(request: NextRequest) {
  const clave = process.env.FOLIO_CLAVE_WEB;
  if (!clave) return NextResponse.next();
  const cabecera = request.headers.get("authorization") ?? "";
  if (cabecera.startsWith("Basic ")) {
    const credenciales = Buffer.from(cabecera.slice(6), "base64").toString("utf8");
    const recibida = credenciales.slice(credenciales.indexOf(":") + 1);  // usuario:contraseña
    const a = Buffer.from(recibida);
    const b = Buffer.from(clave);
    if (a.length === b.length && timingSafeEqual(a, b)) return NextResponse.next();
  }
  return new NextResponse("Folio · acceso con contraseña", {
    status: 401,
    headers: { "WWW-Authenticate": 'Basic realm="Folio", charset="UTF-8"' },
  });
}

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
