import { Table } from "@radix-ui/themes";

export function DataTable({ columns, rows }: { columns: string[]; rows: (string | number)[][] }) {
  return (
    <Table.Root size="1" variant="ghost">
      <Table.Header>
        <Table.Row>
          {columns.map((column, i) => (
            <Table.ColumnHeaderCell key={column} justify={i === 0 ? "start" : "end"}>
              {column}
            </Table.ColumnHeaderCell>
          ))}
        </Table.Row>
      </Table.Header>
      <Table.Body>
        {rows.map((row, r) => (
          <Table.Row key={r}>
            {row.map((cell, i) =>
              i === 0 ? (
                <Table.RowHeaderCell key={i}>{cell}</Table.RowHeaderCell>
              ) : (
                <Table.Cell key={i} justify="end" className="sv-num">
                  {cell}
                </Table.Cell>
              ),
            )}
          </Table.Row>
        ))}
      </Table.Body>
    </Table.Root>
  );
}
