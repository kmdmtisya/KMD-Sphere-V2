import { PortfolioDetail } from "@/components/portfolio/PortfolioDetail";

export const metadata = { title: "Portfolio · WealthSphere" };

export default async function PortfolioPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PortfolioDetail id={id} />;
}
